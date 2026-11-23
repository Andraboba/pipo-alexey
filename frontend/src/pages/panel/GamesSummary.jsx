import { go, useStore } from "../../store.jsx";

const GF = { all: "TCP + UDP", tcp: "только TCP", udp: "только UDP", disabled: "выключен" };

export default function GamesSummary() {
  const { status, split } = useStore();
  const profiles = split?.profiles || [];
  const by = (r) => profiles.filter((p) => p.route === r).map((p) => p.name);
  const parts = [];
  if (by("zapret").length) parts.push("через запрет: " + by("zapret").join(", "));
  if (by("direct").length) parts.push("напрямую: " + by("direct").join(", "));
  return (
    <div className="card">
      <div className="card-title">Игры</div>
      <dl className="kv">
        <dt>Игровой фильтр</dt><dd>{GF[status.zapret.game_filter.mode]}</dd>
        <dt>Профили</dt><dd>{parts.join("; ") || (profiles.length ? "все «не трогать»" : "нет")}</dd>
      </dl>
      <button className="btn" style={{ marginTop: 16 }} onClick={() => go("games")}>Настроить игры</button>
    </div>
  );
}
