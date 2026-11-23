import { post, put } from "../../lib/api.js";
import { tgView } from "../../lib/status.js";
import { useStore } from "../../store.jsx";
import { Button, Lamp, Switch, useAction } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";

export default function TelegramPage() {
  const { status, setTg, refreshStatus } = useStore();
  const tg = status.tg;
  const view = tgView(tg);
  const act = useAction();
  const toast = useToast();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(tg.link);
      toast("Ссылка скопирована");
    } catch {
      toast("Не удалось скопировать — выделите ссылку вручную", true);
    }
  };

  return (
    <section className="tab">
      <div className="engine card">
        <div className="engine-head">
          <Lamp state={view.lamp} />
          <div>
            <div className="eyebrow">TG WS Proxy</div>
            <h1>{view.label}</h1>
            <div className="sub">{view.sub}</div>
          </div>
          <div className="engine-actions">
            <Button kind="solid" disabled={!tg.installed || tg.running} onClick={async () => {
              setTg(await post("/api/tg/start"));
              setTimeout(refreshStatus, 1500);
            }}>Запустить</Button>
            <Button disabled={!tg.running} onClick={async () => setTg(await post("/api/tg/stop"))}>Остановить</Button>
          </div>
        </div>
        <div className="grid2">
          <div className="field">
            <label>Подключение Telegram Desktop</label>
            <div className="linkbox"><code>{tg.link || "— secret появится после первого запуска прокси"}</code></div>
            <div className="row">
              <Button disabled={!tg.link} onClick={async () => { await post("/api/tg/open-link"); toast("Ссылка отправлена в Telegram Desktop"); }}>
                Открыть в Telegram
              </Button>
              <button className="btn ghost" disabled={!tg.link} onClick={copy}>Скопировать ссылку</button>
            </div>
            <p className="hint">
              Вручную: Настройки → Продвинутые → Тип подключения → MTProto, сервер <span className="mono">{tg.host}:{tg.port}</span>.
              В ссылке secret — никому её не отправляйте
            </p>
          </div>
          <div className="field">
            <label>Автозапуск TG WS Proxy</label>
            <Switch checked={tg.autostart} disabled={!tg.installed} onChange={(on) => act(async () => {
              setTg(await put("/api/tg/autostart", { enabled: on }));
              toast(on ? "Автозапуск TG WS Proxy включён" : "Автозапуск TG WS Proxy выключен");
            })}>
              {tg.autostart ? "Включён" : "Выключен"}
            </Switch>
            <p className="hint">Запуск при входе в Windows — то же, что галочка в настройках самого прокси</p>
          </div>
        </div>
        {tg.exe && <div className="engine-foot"><span className="mono">{tg.exe} · {tg.version || "?"}</span></div>}
      </div>
    </section>
  );
}
