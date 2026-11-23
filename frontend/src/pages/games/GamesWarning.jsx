import { useStore } from "../../store.jsx";

export default function GamesWarning() {
  const { status, split } = useStore();
  if (!split) return null;
  const z = status.zapret;
  const through = split.profiles.filter((p) => p.route === "zapret");
  const msgs = [];
  if (through.length && z.game_filter.mode === "disabled")
    msgs.push(`«${through[0].name}» идёт через запрет, но игровой фильтр выключен — обходиться будут только порты 80 и 443`);
  if (through.length && z.ipset_mode !== "loaded")
    msgs.push(`Режим IPSet «${z.ipset_mode === "none" ? "Никакие" : "Все"}» — профили «через запрет» по IP сейчас не действуют`);
  if (!msgs.length) return null;
  return <div className="banner warn inline">{msgs.map((m) => <div key={m}>{m}</div>)}</div>;
}
