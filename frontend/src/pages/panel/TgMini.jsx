import { tgView } from "../../lib/status.js";
import { go, useStore } from "../../store.jsx";
import { Button, Lamp } from "../../ui/controls.jsx";

export default function TgMini() {
  const { status } = useStore();
  const tg = status.tg;
  const view = tgView(tg);
  return (
    <div className="card tg-mini">
      <Lamp state={view.lamp} small />
      <div className="grow">
        <div className="eyebrow">TG WS Proxy</div>
        <div>{view.label}{tg.version ? " · " + tg.version : ""}</div>
      </div>
      <Button onClick={() => go("telegram")}>Открыть</Button>
    </div>
  );
}
