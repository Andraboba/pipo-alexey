import { useEffect, useState } from "react";
import { put } from "../../lib/api.js";
import { useStore } from "../../store.jsx";
import { Button, Seg, Switch, useAction } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";

const MODES = [
  { v: "all", label: "TCP + UDP" },
  { v: "tcp", label: "Только TCP" },
  { v: "udp", label: "Только UDP" },
];

export default function GameFilterCard() {
  const { status, applyResp } = useStore();
  const gf = status.zapret.game_filter;
  const on = gf.mode !== "disabled";
  const [mode, setMode] = useState(on ? gf.mode : "all");
  const [tcp, setTcp] = useState(gf.tcp);
  const [udp, setUdp] = useState(gf.udp);
  const act = useAction();
  const toast = useToast();
  useEffect(() => { if (gf.mode !== "disabled") setMode(gf.mode); }, [gf.mode]);

  const save = (m, msg) => put("/api/zapret/game-filter", { mode: m, tcp, udp }).then((r) => { applyResp(r); toast(msg); });

  return (
    <div className={"card gf-card" + (on ? "" : " off")}>
      <div className="gf-row">
        <div className="grow">
          <div className="card-title">Игровой фильтр</div>
          <p className="hint" style={{ margin: 0 }}>Обход на портах выше 1024 для адресов из IPSet. Без него игре помогают только порты 80 и 443</p>
        </div>
        <Switch checked={on} onChange={(v) => act(() => save(v ? mode : "disabled", v ? "Игровой фильтр включён" : "Игровой фильтр выключен"))}>
          {on ? "Включён" : "Выключен"}
        </Switch>
      </div>
      <div className="gf-row">
        <Seg options={MODES} value={mode} onChange={(m) => {
          setMode(m);
          if (on) act(() => save(m, "Игровой фильтр: " + MODES.find((x) => x.v === m).label));
        }} />
        <details className="ports">
          <summary className="link">Порты</summary>
          <div className="row" style={{ marginTop: 8 }}>
            <label className="mini">TCP <input className="mono" value={tcp} onChange={(e) => setTcp(e.target.value)} spellCheck={false} /></label>
            <label className="mini">UDP <input className="mono" value={udp} onChange={(e) => setUdp(e.target.value)} spellCheck={false} /></label>
            <Button small onClick={() => save(gf.mode, "Порты сохранены")}>Сохранить порты</Button>
          </div>
        </details>
      </div>
    </div>
  );
}
