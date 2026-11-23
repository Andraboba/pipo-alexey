import { useStore } from "../store.jsx";
import { IconNavCollapse, IconNavExpand } from "../ui/icons.jsx";

export default function Nav({ tabs, active, collapsed, onToggle }) {
  const { updates } = useStore();
  const hasUpdate = updates?.zapret?.newer || updates?.tg?.newer;
  return (
    <nav className={"nav" + (collapsed ? " collapsed" : "")}>
      {tabs.map((t) => (
        <a
          key={t.id}
          href={"#" + t.id}
          className={t.id === active ? "active" : ""}
          aria-current={t.id === active ? "page" : undefined}
          aria-label={t.label}
        >
          <t.Icon />
          <span className="label">{t.label}</span>
          {t.id === "updates" && hasUpdate && <span className="dot" />}
        </a>
      ))}
      <button
        type="button"
        className="nav-toggle"
        onClick={onToggle}
        aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
        aria-expanded={!collapsed}
      >
        {collapsed ? <IconNavExpand /> : <IconNavCollapse />}
        <span className="label">{collapsed ? "Развернуть меню" : "Свернуть"}</span>
      </button>
    </nav>
  );
}
