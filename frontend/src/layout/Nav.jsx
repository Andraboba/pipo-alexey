import { useStore } from "../store.jsx";

export default function Nav({ tabs, active }) {
  const { updates } = useStore();
  const hasUpdate = updates?.zapret?.newer || updates?.tg?.newer;
  return (
    <nav className="nav">
      {tabs.map((t) => (
        <a key={t.id} href={"#" + t.id} className={t.id === active ? "active" : ""} aria-current={t.id === active ? "page" : undefined}>
          {t.label}
          {t.id === "updates" && hasUpdate && <span className="dot" />}
        </a>
      ))}
    </nav>
  );
}
