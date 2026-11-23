import { useEffect, useMemo, useState } from "react";
import { get, post } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button, Switch } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import TargetPicker from "./TargetPicker.jsx";
import StrategyPicker from "./StrategyPicker.jsx";
import ScanResults from "./ScanResults.jsx";
import "../../styles/scan.css";

// по умолчанию: то, ради чего обычно ставят запрет, и все игры пользователя
const DEFAULT_GROUPS = /^(Discord|YouTube|Игра:)/;
const DPI_SUITE_SIZE = 36;

export default function ScanPage() {
  const { job, watchJob, status } = useStore();
  const confirm = useConfirm();
  const [info, setInfo] = useState(null);
  const [picked, setPicked] = useState(new Set());
  const [strategies, setStrategies] = useState(new Set());
  const [custom, setCustom] = useState("");
  const [dpi, setDpi] = useState(false);

  const load = () => get("/api/scan/targets").then((d) => {
    setInfo(d);
    setPicked((prev) => prev.size ? prev : new Set(d.targets.filter((t) => DEFAULT_GROUPS.test(t.group)).map((t) => t.id)));
    setStrategies((prev) => prev.size ? prev : new Set(d.strategies));
  });
  useEffect(() => { load(); }, []);

  const scanJob = job?.kind === "scan" ? job : null;
  const running = scanJob?.state === "running";
  useEffect(() => { if (scanJob && scanJob.state !== "running") load(); }, [scanJob?.state]);

  const customCount = useMemo(() => custom.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length, [custom]);
  const targetCount = picked.size + customCount + (dpi ? DPI_SUITE_SIZE : 0);
  const minutes = Math.max(1, Math.round(((strategies.size || 1) + 1) * (dpi ? 9 : 7) / 60));

  const start = async () => {
    const ok = await confirm({
      title: `Проверить ${strategies.size} стратегий на ${targetCount} целях?`,
      ok: "Начать подбор",
      body: (
        <ul>
          <li>Займёт около {minutes} мин. Всё это время интернет может подтормаживать.</li>
          <li>Запрет остановится; каждая стратегия запустится на пару секунд, IPSet временно станет «Все».</li>
          <li>В конце всё вернётся как было{status.zapret.service === "running" ? ", служба запустится снова" : " — служба останется выключенной"}.</li>
          <li>Ничего не применяется само: лучшую стратегию вы выберете кнопкой «Применить».</li>
        </ul>
      ),
    });
    if (!ok) return;
    watchJob(await post("/api/scan", { strategies: [...strategies], target_ids: [...picked], custom, dpi }));
  };

  if (!info) return <section className="tab"><div className="empty">Загрузка…</div></section>;
  const result = scanJob?.result || info.last;

  return (
    <section className="tab">
      <div className="intro">
        <h2>Подбор стратегии</h2>
        <p>
          Запускаю каждую стратегию по очереди и проверяю, доходят ли данные до выбранных сайтов, IP и сетей.
          Сначала — прогон без запрета, чтобы было видно, что вообще заблокировано
        </p>
      </div>

      <div className="scan-setup">
        <TargetPicker targets={info.targets} picked={picked} setPicked={setPicked} disabled={running} />
        <div className="stack">
          <div className="card">
            <div className="card-title">Свои цели</div>
            <p className="hint">Домен, ссылка, IP или IP:порт — по одной в строке</p>
            <textarea className="mono" rows={5} spellCheck={false} disabled={running} value={custom}
              onChange={(e) => setCustom(e.target.value)} placeholder={"chatgpt.com\n185.40.64.65:443\n[2a03:2880::1]:443"} />
          </div>
          <div className="card">
            <Switch checked={dpi} disabled={running} onChange={setDpi}>Проверка заморозки 16–20 КБ</Switch>
            <p className="hint" style={{ marginBottom: 0 }}>
              36 серверов из набора hyperion-cs: отправляю 64 КБ и смотрю, не замерло ли соединение — так выглядит
              замедление YouTube и Cloudflare
            </p>
          </div>
          <StrategyPicker all={info.strategies} picked={strategies} setPicked={setStrategies} current={info.current} disabled={running} />
        </div>
      </div>

      <div className="scan-bar card">
        <div className="grow">
          <b>{targetCount}</b> {targetCount === 1 ? "цель" : "целей"} · <b>{strategies.size}</b> стратегий · около {minutes} мин
        </div>
        {running ? (
          <Button onClick={async () => post(`/api/jobs/${scanJob.id}/cancel`)} disabled={scanJob.cancelled}>
            {scanJob.cancelled ? "Останавливаю…" : "Остановить"}
          </Button>
        ) : (
          <Button kind="solid" disabled={!targetCount || !strategies.size || !status.admin} onClick={start}>Начать подбор</Button>
        )}
      </div>

      {result && <ScanResults result={result} running={running} job={scanJob} current={info.current} onApplied={load} />}
    </section>
  );
}
