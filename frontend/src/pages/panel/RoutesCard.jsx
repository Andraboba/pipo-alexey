import { domains, fmt, nets } from "../../lib/format.js";
import { domainsThroughZapret, flowsFor, netTotal } from "../../lib/routes.js";
import { useStore } from "../../store.jsx";

function Lane({ route, title, flows }) {
  const total = netTotal(flows);
  const max = Math.max(1, ...flows.filter((f) => f.unit === "nets").map((f) => f.n));
  return (
    <div className={"lane " + route}>
      <div className="lane-title">
        <b>{title}</b>
        {total > 0 && <span className="lane-total"><span className="num">{fmt(total)}</span> {nets(total)}</span>}
      </div>
      {flows.length ? flows.map((f) => (
        <div className="flow" key={f.key}>
          <div className="what">{f.what}{f.sub && <span>{f.sub}</span>}</div>
          <div className="n"><span className="num">{fmt(f.n)}</span> {f.unit === "nets" ? nets(f.n) : domains(f.n)}</div>
          {f.unit === "nets" && <div className="meter"><i style={{ width: Math.max(1, (f.n / max) * 100) + "%" }} /></div>}
        </div>
      )) : <div className="none">Ничего — добавьте правило во вкладке «Сплит»</div>}
    </div>
  );
}

/** Схема маршрутов — единственное цветное место пульта. */
export default function RoutesCard() {
  const { split, status } = useStore();
  if (!split) return null;
  const mode = status.zapret.ipset_mode;
  const z = flowsFor(split, "zapret", mode);
  const d = flowsFor(split, "direct", mode);
  const nz = netTotal(z);
  const nd = netTotal(d);
  const base = z.find((f) => f.key === "base")?.n || 0;
  const total = Math.max(1, nz + nd);
  const domZ = domainsThroughZapret(split);
  const seg = (cls, n, title) => n > 0 && <i className={cls} style={{ flex: n / total }} title={title} />;

  return (
    <div className="card routes" data-tour="routes">
      <div className="routes-head">
        <div className="card-title">Маршруты</div>
        <span className="sub">
          через запрет <span className="num">{fmt(nz)}</span> {nets(nz)} и <span className="num">{fmt(domZ)}</span> {domains(domZ)}
          {" · "}напрямую <span className="num">{fmt(nd)}</span>
        </span>
      </div>
      <div className="routes-bar">
        {seg("z", base, "Списки Flowseal")}
        {seg("z2", nz - base, "Игры и ваши правила через запрет")}
        {seg("d", nd, "Напрямую")}
      </div>
      <div className="lanes">
        <Lane route="zapret" title="Через запрет" flows={z} />
        <Lane route="direct" title="Напрямую" flows={d} />
      </div>
    </div>
  );
}
