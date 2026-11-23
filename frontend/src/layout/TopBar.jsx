import { go, useStore } from "../store.jsx";
import { Logo } from "../ui/icons.jsx";
import { zapretView, tgView } from "../lib/status.js";

function LampPill({ label, view, to }) {
  return (
    <button className="lamp" onClick={() => go(to)}>
      <i className={view.lamp ? "on-" + view.lamp : ""} />
      <span>{label}</span>
      <b>{view.on ? "вкл" : "выкл"}</b>
    </button>
  );
}

export default function TopBar() {
  const { status, updates } = useStore();
  const hasUpdate = updates?.zapret?.newer || updates?.tg?.newer;
  return (
    <header className="topbar">
      <div className="brand">
        <Logo />
        <span>Пипо <span className="dim">Алексей</span></span>
      </div>
      {status && (
        <div className="lamps">
          <LampPill label="Запрет" view={zapretView(status.zapret)} to="panel" />
          <LampPill label="Telegram" view={tgView(status.tg)} to="telegram" />
        </div>
      )}
      {hasUpdate && <button className="update-pill" onClick={() => go("updates")}>Есть обновление</button>}
    </header>
  );
}
