import { useEffect, useMemo, useState } from "react";
import { del, get, post } from "../../lib/api.js";
import { plural } from "../../lib/format.js";
import { go, useStore } from "../../store.jsx";
import { Button, Seg, Switch } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import TargetPicker from "../scan/TargetPicker.jsx";
import JobConsole from "../updates/JobConsole.jsx";
import "../../styles/scan.css";
import "../../styles/diag.css";

// игры — как контроль: их сайты обычно открыты, и найденная стратегия не должна их сломать
const DEFAULT_GROUPS = /^(Discord|YouTube|Игра:)/;
const DPI_SUITE_SIZE = 36; // серверов в наборе hyperion-cs/dpi-checkers
const HOURS = [{ v: 1, label: "1 ч" }, { v: 3, label: "3 ч" }, { v: 6, label: "6 ч" }, { v: 8, label: "8 ч" }];

const hm = (sec) => {
  const m = Math.max(0, Math.round(sec / 60));
  return m >= 60 ? `${Math.floor(m / 60)} ч ${m % 60} мин` : `${m} мин`;
};

export default function EvolvePage() {
  const { job, watchJob, status, busy, setZapret, setRestartNeeded } = useStore();
  const toast = useToast();
  const confirm = useConfirm();
  const [info, setInfo] = useState(null);
  const [picked, setPicked] = useState(new Set());
  const [custom, setCustom] = useState("");
  const [dpi, setDpi] = useState(false);
  const [hours, setHours] = useState(6);

  const load = () => get("/api/evolve").then((d) => {
    d = { ...d, targets: d.targets.filter((t) => t.kind !== "ip") };  // IP и ping по TLS не проверить
    setInfo(d);
    setPicked((prev) => prev.size ? prev : new Set(d.targets.filter((t) => DEFAULT_GROUPS.test(t.group)).map((t) => t.id)));
  }).catch((e) => toast(e.message, true));
  useEffect(() => { load(); }, []);

  const evoJob = job?.kind === "evolve" ? job : null;
  const running = evoJob?.state === "running";
  useEffect(() => { if (evoJob && !running) load(); }, [evoJob?.state]);

  const customCount = useMemo(() => custom.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length, [custom]);
  const count = picked.size + customCount + (dpi ? DPI_SUITE_SIZE : 0);

  if (!info) return <section className="tab"><div className="empty">Загрузка…</div></section>;

  if (info.engine !== "zapret2") {
    return (
      <section className="tab">
        <div className="intro"><h2>Эволюция стратегий</h2></div>
        <div className="card stack">
          <p>Эволюция работает с движком <b>zapret2</b>: его стратегии — цепочки шагов на Lua, их удобно скрещивать и мутировать.</p>
          <div className="row">
            <Button kind="solid" onClick={() => go("panel")}>Переключить движок на «Пульте»</Button>
            <Button onClick={() => go("updates")}>Установить zapret2</Button>
          </div>
        </div>
      </section>
    );
  }

  const start = async (resume) => {
    const until = new Date(Date.now() + hours * 3600 * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
    const ok = await confirm({
      title: resume ? `Продолжить поиск ещё ${hours} ч?` : `Искать стратегию ${hours} ч, до ${until}?`,
      ok: resume ? "Продолжить" : "Начать",
      body: (
        <ul>
          <li>Запрет остановится; всё это время winws2 запускается с разными вариантами по нескольку секунд, интернет будет то работать, то нет. Можно ложиться спать.</li>
          <li>Компьютер не уснёт, пока идёт поиск. Не закрывайте Пипо Алексея.</li>
          <li>Пропадёт интернет — поиск подождёт, а не испортит результаты.</li>
          <li>В конце служба вернётся как была. Найденное ничего не меняет само: утром выберите стратегию и нажмите «Применить».</li>
          {resume && <li>Продолжу на тех же целях, что и в прошлый раз.</li>}
        </ul>
      ),
    });
    if (!ok) return;
    watchJob(await post("/api/evolve", { target_ids: [...picked], custom, dpi, hours, resume }));
  };

  const apply = async (b) => {
    const ok = await confirm({
      title: "Применить найденную стратегию?",
      ok: "Применить",
      body: (
        <>
          <p>Сохраню её как <code>general (PIPO EVO N).bat</code> в папке zapret2 — QUIC, Discord и игры как в «SIMPLE FAKE», а для TLS
            (YouTube, сайты из списков и IPSet) — найденная цепочка:</p>
          <p className="mono">{b.steps.join(" → ")}</p>
          <p>Ваши собственные цели (если были) добавлю в «Сплит» через запрет — иначе стратегия их не тронет.</p>
          <p>{status.zapret.service !== null ? "Служба переключится на неё. Если запрет работает — перезапустите его." : "Служба будет создана без автозапуска и не запустится сама."}</p>
        </>
      ),
    });
    if (!ok) return;
    const { strategy, added } = await post("/api/evolve/save", { key: b.key });
    if (added?.length) toast("В сплит «через запрет» добавлено: " + added.join(", "));
    const z = await post("/api/zapret/install", { strategy, start: false });
    setZapret(z);
    if (z.service === "running") setRestartNeeded(true);
    toast("Стратегия применена: " + strategy);
  };

  const res = evoJob?.result || info.last;

  return (
    <section className="tab">
      <div className="intro">
        <h2>Эволюция стратегий</h2>
        <p>
          Приложение само ищет обход под вашего провайдера. Стратегия для TLS — цепочка шагов (фейки, разрезание пакета,
          способ обмана DPI); готовые стратегии сборки становятся первым поколением, лучшие скрещиваются и мутируют,
          каждый вариант проверяется на ваших целях. Запустите на ночь — утром выберите лучшую
        </p>
      </div>

      {!running && (
        <>
          <div className="scan-setup">
            <TargetPicker targets={info.targets} picked={picked} setPicked={setPicked} disabled={running} />
            <div className="stack">
              <div className="card">
                <div className="card-title">Свои цели</div>
                <p className="hint">Сайты, которые у вас не открываются, — по одному в строке. Нужен хотя бы один заблокированный</p>
                <textarea className="mono" rows={5} spellCheck={false} value={custom}
                  onChange={(e) => setCustom(e.target.value)} placeholder={"youtube.com\nx.com"} />
              </div>
              <div className="card">
                <Switch checked={dpi} onChange={setDpi}>Проверка заморозки 16–20 КБ</Switch>
                <p className="hint" style={{ marginBottom: 0 }}>36 серверов hyperion-cs — дольше каждая проверка, зато видно замедление Cloudflare и YouTube</p>
              </div>
              <div className="card">
                <div className="card-title">Сколько искать</div>
                <Seg options={HOURS} value={hours} onChange={setHours} />
                <p className="hint" style={{ marginBottom: 0 }}>
                  Один вариант — около 10 секунд, за час ~350. Найдёт стратегию, которая чинит всё и ничего не ломает, — остановится раньше
                </p>
              </div>
            </div>
          </div>
          <div className="scan-bar card">
            <div className="grow">
              <b>{count}</b> {plural(count, "цель", "цели", "целей")} · до {hours} ч
            </div>
            {info.can_resume && <Button disabled={!status.admin || busy} onClick={() => start(true)}>Продолжить прошлый</Button>}
            <Button kind="solid" disabled={!count || !status.admin || busy} onClick={() => start(false)}>Начать поиск</Button>
          </div>
        </>
      )}

      {!running && <ImportCard imports={info.imports || []} onChange={load} />}
      {res && <Results res={res} job={running ? evoJob : null} current={info.current} onApply={apply} />}
      {evoJob && <JobConsole job={evoJob} />}
    </section>
  );
}

function Results({ res, job, current, onApply }) {
  const { status } = useStore();
  const toast = useToast();
  const share = async (b) => {
    try {
      await navigator.clipboard.writeText(b.code);
      toast("Код скопирован — отправьте его другу");
    } catch {
      window.prompt?.("Скопируйте код:", b.code);
    }
  };
  const now = Date.now() / 1000;
  const left = res.deadline - now;
  const hist = res.history || [];
  const maxFit = Math.max(1e-6, ...hist.map((h) => h.fitness));
  return (
    <div className="card stack">
      <div className="list-head">
        <div className="card-title">
          {job ? "Идёт поиск" : res.phase === "done" ? "Результат" : "Прошлый поиск (прерван)"}
        </div>
        {job && (
          <Button onClick={() => post(`/api/jobs/${job.id}/cancel`)} disabled={job.cancelled}>
            {job.cancelled ? "Останавливаю…" : "Остановить"}
          </Button>
        )}
      </div>
      {job && <div className="progress"><i style={{ width: Math.round((job.progress || 0) * 100) + "%" }} /></div>}
      <div className="evo-stats">
        <div><b>{res.generation}</b><span>поколение</span></div>
        <div><b>{res.evaluated}</b><span>вариантов проверено</span></div>
        <div><b>{res.blocked_count}</b><span>заблокировано без запрета</span></div>
        <div><b>{hm(job ? now - res.started : res.elapsed)}</b><span>{job ? "идёт" : "искали"}</span></div>
        {job && left > 0 && <div><b>{hm(left)}</b><span>осталось</span></div>}
      </div>
      {res.blocked?.length > 0 && <p className="hint">Чиним: {res.blocked.join(", ")}. Не ломаем: {res.controls.join(", ") || "—"}</p>}
      {res.dead?.length > 0 && <p className="hint">Не открываются ни без запрета, ни с одним вариантом — не учитываются: {res.dead.join(", ")}</p>}
      {hist.length > 1 && (
        <div className="evo-spark" title="Лучший результат по поколениям">
          {hist.slice(-120).map((h, i) => <i key={i} className={h.fixed >= res.blocked_count && !h.broke ? "top" : ""}
            style={{ height: Math.max(4, (Math.max(0, h.fitness) / maxFit) * 100) + "%" }} />)}
        </div>
      )}
      <div>
        {res.best.length === 0 && <div className="empty">Пока ничего не проверено</div>}
        {res.best.map((b, i) => (
          <div key={b.key} className="evo-row">
            <span className="rank">{i + 1}</span>
            <div className="evo-steps">
              {b.steps.map((s, j) => (
                <span key={j} className="evo-steps">
                  {j > 0 && <span className="arrow">→</span>}
                  <span className="tag">{s}</span>
                </span>
              ))}
            </div>
            <div className="evo-meta">
              <span className={b.fixed >= res.blocked_count && !b.broke ? "fixed" : ""}>чинит {b.fixed} из {res.blocked_count}</span>
              <span className={b.broke ? "t-bad" : ""}>{b.broke ? `ломает ${b.broke}` : "ничего не ломает"}</span>
              <span>{b.evals > 1 ? `проверено ${b.evals} раза` : "проверено 1 раз"} · {b.origin}</span>
            </div>
            <div className="row">
              {b.code && <Button small plain kind="link" onClick={() => share(b)}>Поделиться</Button>}
              <Button small kind={i === 0 ? "solid" : ""} disabled={!status.admin || !!job || b.fixed === 0} onClick={() => onApply(b)}>Применить</Button>
            </div>
          </div>
        ))}
      </div>
      {current && <p className="hint">Сейчас в службе: {current}</p>}
    </div>
  );
}

/** Код от друга: сразу стратегией или в стартовое поколение эволюции. */
function ImportCard({ imports, onChange }) {
  const { status, busy, setZapret, setRestartNeeded } = useStore();
  const toast = useToast();
  const [code, setCode] = useState("");
  const act = (save) => async () => {
    try {
      if (save) {
        const { strategy, added } = await post("/api/evolve/import", { code, save: true });
        if (added?.length) toast("В сплит «через запрет» добавлено: " + added.join(", "));
        const z = await post("/api/zapret/install", { strategy, start: false });
        setZapret(z);
        if (z.service === "running") setRestartNeeded(true);
        toast("Стратегия друга сохранена и выбрана в службе: " + strategy);
      } else {
        await post("/api/evolve/import", { code, save: false });
        toast("Добавлено в стартовое поколение следующего поиска");
      }
      setCode("");
      onChange();
    } catch (e) {
      toast(e.message, true);
    }
  };
  return (
    <div className="card stack">
      <div className="card-title">Код от друга {imports.length > 0 && <span className="count">{imports.length} в стартовом поколении</span>}</div>
      <p className="hint">
        Строка вида <code>pipo:v1:fake:…|multisplit:…</code> — её даёт кнопка «Поделиться». Что сработало у друга, у вас
        может не сработать: DPI у провайдеров разный. С другого компьютера в той же сети — применяйте сразу: стратегия
        будет точно такой же, а сайты из «своих целей» встанут в «Сплит». У друга с тем же провайдером надёжнее положить
        код в стартовое поколение — эволюция начнёт с него и доведёт под его подключение
      </p>
      <textarea className="mono" rows={2} spellCheck={false} value={code} onChange={(e) => setCode(e.target.value)}
        placeholder="pipo:v1:…" />
      <div className="row">
        <Button disabled={!code.trim() || !status.admin || busy} onClick={act(false)}>В стартовое поколение</Button>
        <Button disabled={!code.trim() || !status.admin || busy} onClick={act(true)}>Сразу применить</Button>
        {imports.length > 0 && (
          <Button plain kind="link danger" disabled={!status.admin || busy}
            onClick={async () => { await del("/api/evolve/imports"); onChange(); }}>Очистить импорт</Button>
        )}
      </div>
      {imports.length > 0 && (
        <div className="tags">{imports.map((i) => <span key={i.code} className="tag" title={i.steps.join(" → ")}>{i.note || i.steps.join(" → ")}</span>)}</div>
      )}
    </div>
  );
}
