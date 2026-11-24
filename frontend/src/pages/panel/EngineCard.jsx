import { useEffect, useState } from "react";
import { post, put } from "../../lib/api.js";
import { zapretView } from "../../lib/status.js";
import { go, useStore } from "../../store.jsx";
import { Button, Lamp, Seg, Switch, useAction } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";

export default function EngineCard() {
  const { status, setZapret, setRestartNeeded } = useStore();
  const z = status.zapret;
  const view = zapretView(z);
  const toast = useToast();
  const confirm = useConfirm();
  const act = useAction();
  const [strategy, setStrategy] = useState(z.strategy || z.strategies[0] || "");
  // у движков разные стратегии: после переключения выбор должен быть из нового списка
  useEffect(() => {
    setStrategy(z.strategy && z.strategies.includes(z.strategy) ? z.strategy : z.strategies[0] || "");
  }, [z.strategy, z.engine, z.strategies.join("|")]);

  const installed = z.service !== null;
  const running = z.service === "running";

  const run = (path, msg) => async () => {
    setZapret(await post(path));
    if (path.endsWith("restart") || path.endsWith("start")) setRestartNeeded(false);
    toast(msg);
  };

  const install = async () => {
    const ok = await confirm({
      title: installed ? `Переключить службу на «${strategy}»?` : `Установить службу со стратегией «${strategy}»?`,
      body: installed
        ? "Аргументы службы пересоберутся из выбранного .bat. Если запрет работает — перезапустите его после этого."
        : <>Служба будет создана <b>без автозапуска</b> и <b>не запустится</b> сама — включите её кнопкой «Запустить», когда понадобится.</>,
      ok: installed ? "Переключить" : "Установить",
    });
    if (!ok) return;
    const nz = await post("/api/zapret/install", { strategy, start: false });
    setZapret(nz);
    if (nz.service === "running") setRestartNeeded(true);
    toast("Служба настроена: " + strategy);
  };

  const remove = async () => {
    const ok = await confirm({
      title: "Удалить службу zapret?",
      body: "Запрет остановится, служба и драйвер WinDivert будут удалены. Файлы в папке запрета и ваши списки останутся.",
      ok: "Удалить", danger: true,
    });
    if (ok) await act(async () => { setZapret(await post("/api/zapret/remove")); toast("Служба удалена"); });
  };

  const switchEngine = async (id) => {
    const e = z.engines.find((x) => x.id === id);
    if (!e.exists) {
      const ok = await confirm({
        title: `${e.title} не установлен`,
        body: <>В <code>{e.dir}</code> нет <code>bin\{e.exe}</code>. Установить его можно во вкладке «Обновления» — запрет при этом не остановится.</>,
        ok: "Открыть «Обновления»",
      });
      if (ok) go("updates");
      return;
    }
    const ok = await confirm({
      title: `Переключиться на ${e.title}?`,
      body: (
        <ul>
          <li>Запрет остановится вместе с драйвером WinDivert: два движка вместе не работают.</li>
          <li>Ваши сплит-правила, игры и игровой фильтр перенесутся в папку <code>{e.dir}</code>.</li>
          {installed && <li>Служба перенастроится на стратегию {e.title}{running ? " и запустится снова" : ", запускать её не буду"}. Какая лучше — покажет «Подбор».</li>}
        </ul>
      ),
      ok: "Переключить",
    });
    if (!ok) return;
    await act(async () => {
      const r = await put("/api/zapret/engine", { engine: id });
      setZapret(r.status);
      setRestartNeeded(false);
      toast(`Движок: ${e.title}` + (r.strategy ? ` · ${r.strategy}` : ""));
    });
  };

  const autostart = (on) => act(async () => {
    setZapret(await put("/api/zapret/autostart", { enabled: on }));
    toast(on ? "Автозапуск запрета включён" : "Автозапуск запрета выключен");
  });

  return (
    <div className="engine card" data-tour="engine">
      <div className="engine-head">
        <Lamp state={view.lamp} />
        <div>
          <div className="eyebrow">Служба zapret · {z.engine_title}</div>
          <h1>{view.label}</h1>
          <div className="sub">{view.sub}</div>
        </div>
        <div className="engine-actions">
          <Button kind="solid" disabled={!installed || running} onClick={run("/api/zapret/start", "Запрет запущен")}>Запустить</Button>
          <Button disabled={!running && !z.winws_running} onClick={run("/api/zapret/stop", "Запрет остановлен")}>Остановить</Button>
          <Button disabled={!running} onClick={run("/api/zapret/restart", "Запрет перезапущен")}>Перезапустить</Button>
        </div>
      </div>

      <div className="field">
        <div className="field-label">Движок</div>
        <Seg value={z.engine} onChange={switchEngine}
          options={z.engines.map((e) => ({ v: e.id, label: e.title + (e.exists ? "" : " · не установлен") }))} />
        <p className="hint">Работает один из двух. zapret2 — новая версия запрета от bol-van со стратегиями на Lua; если с одним сайты не открываются, попробуйте другой</p>
      </div>

      <div className="grid2">
        <div className="field">
          <label htmlFor="z-strategy">Стратегия</label>
          <div className="row">
            <select id="z-strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {z.strategies.map((s) => <option key={s}>{s}</option>)}
            </select>
            <Button onClick={install}>{installed ? "Сменить стратегию" : "Установить службу"}</Button>
            <Button onClick={() => go("scan")}>Подбор</Button>
          </div>
          <p className="hint">Не знаете, какую выбрать, или сайт не открывается — «Подбор» проверит все стратегии на нужных сайтах</p>
        </div>
        <div className="field">
          <div className="field-label">Автозапуск запрета</div>
          <Switch checked={z.autostart} disabled={!installed} onChange={autostart}>
            {!installed ? "Служба не установлена" : z.autostart ? "Включён" : "Выключен"}
          </Switch>
          <p className="hint">Выключен — запрет стартует только по кнопке «Запустить»</p>
        </div>
      </div>

      <div className="engine-foot">
        <span className="mono">{z.engine_title} {z.version || "?"} · {z.dir}</span>
        {installed && <Button plain kind="link danger" onClick={remove}>Удалить службу</Button>}
      </div>
    </div>
  );
}
