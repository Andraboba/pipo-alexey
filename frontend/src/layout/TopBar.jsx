import { useCallback, useState } from "react";
import { go, useStore } from "../store.jsx";
import { Logo } from "../ui/icons.jsx";
import { zapretView, tgView } from "../lib/status.js";
import { cssRect } from "../lib/uiScale.js";
import LampMenu from "./LampMenu.jsx";

function LampPill({ label, view, to, kind, open, onMenu, onClose }) {
  return (
    <button
      className={"lamp" + (open ? " open" : "")}
      data-kind={kind}
      onClick={() => { onClose(); go(to); }}
      onContextMenu={(e) => { e.preventDefault(); onMenu(kind, cssRect(e.currentTarget)); }}
      title="Клик — открыть вкладку, правая кнопка — включить или выключить"
      aria-haspopup="menu"
      aria-expanded={open}
    >
      <i className={view.lamp ? "on-" + view.lamp : ""} />
      <span>{label}</span>
      <b>{view.on ? "вкл" : "выкл"}</b>
    </button>
  );
}

export default function TopBar() {
  const { status, updates } = useStore();
  const hasUpdate = updates?.zapret?.newer || updates?.tg?.newer;
  const [menu, setMenu] = useState(null);
  const close = useCallback(() => setMenu(null), []);
  const onMenu = (kind, anchor) => setMenu((m) => (m?.kind === kind ? null : { kind, anchor }));
  return (
    <header className="topbar">
      <div className="brand">
        <Logo />
        <span>Пипо <span className="dim">Алексей</span></span>
      </div>
      {status && (
        <div className="lamps" data-tour="lamps">
          <LampPill label="Запрет" kind="zapret" view={zapretView(status.zapret)} to="panel" open={menu?.kind === "zapret"} onMenu={onMenu} onClose={close} />
          <LampPill label="Прокси TG" kind="tg" view={tgView(status.tg)} to="telegram" open={menu?.kind === "tg"} onMenu={onMenu} onClose={close} />
        </div>
      )}
      {hasUpdate && <button className="update-pill" onClick={() => go("updates")}>Есть обновление</button>}
      {menu && status && <LampMenu kind={menu.kind} anchor={menu.anchor} onClose={close} />}
    </header>
  );
}
