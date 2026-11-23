import { useEffect, useState } from "react";
import { post, put } from "../../lib/api.js";
import { zapretView } from "../../lib/status.js";
import { go, useStore } from "../../store.jsx";
import { Button, Lamp, Switch, useAction } from "../../ui/controls.jsx";
import { useConfirm } from "../../ui/ConfirmDialog.jsx";
import { useToast } from "../../ui/Toasts.jsx";

export default function EngineCard() {
  const { status, setZapret, setRestartNeeded } = useStore();
  const z = status.zapret;
  const view = zapretView(z);
  const toast = useToast();
  const confirm = useConfirm();
  const act = useAction();
  const [strategy, setStrategy] = useState(z.strategy || "general");
  useEffect(() => { if (z.strategy) setStrategy(z.strategy); }, [z.strategy]);

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

  const autostart = (on) => act(async () => {
    setZapret(await put("/api/zapret/autostart", { enabled: on }));
    toast(on ? "Автозапуск запрета включён" : "Автозапуск запрета выключен");
  });

  return (
    <div className="engine card">
      <div className="engine-head">
        <Lamp state={view.lamp} />
        <div>
          <div className="eyebrow">Служба zapret</div>
          <h1>{view.label}</h1>
          <div className="sub">{view.sub}</div>
        </div>
        <div className="engine-actions">
          <Button kind="solid" disabled={!installed || running} onClick={run("/api/zapret/start", "Запрет запущен")}>Запустить</Button>
          <Button disabled={!running && !z.winws_running} onClick={run("/api/zapret/stop", "Запрет остановлен")}>Остановить</Button>
          <Button disabled={!running} onClick={run("/api/zapret/restart", "Запрет перезапущен")}>Перезапустить</Button>
        </div>
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
        <span className="mono">zapret {z.version || "?"} · {z.dir}</span>
        {installed && <Button plain kind="link danger" onClick={remove}>Удалить службу</Button>}
      </div>
    </div>
  );
}
