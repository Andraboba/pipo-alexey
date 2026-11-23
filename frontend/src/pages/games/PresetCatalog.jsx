import { post } from "../../lib/api.js";
import { ROUTE_LABEL } from "../../lib/format.js";
import { useStore } from "../../store.jsx";
import { Button } from "../../ui/controls.jsx";
import { useToast } from "../../ui/Toasts.jsx";

const CONF = { high: "точный", medium: "проверен частично", low: "приблизительный" };

function Preset({ p }) {
  const { setSplit } = useStore();
  const toast = useToast();
  const shown = p.domains.slice(0, 3);
  return (
    <div className={"card preset" + (p.added ? " added" : "")}>
      <div className="head">
        <b>{p.name}</b>
        <span className={"conf " + p.confidence}>{CONF[p.confidence]}</span>
      </div>
      <div className="tags">
        {shown.map((d) => <span className="tag" key={d}>{d}</span>)}
        {p.domains.length > shown.length && <span className="tag">+{p.domains.length - shown.length}</span>}
        {p.asns.map((a) => <span className="tag" key={a.asn} title={a.holder}>AS{a.asn}</span>)}
      </div>
      {p.note && <p>{p.note}</p>}
      {p.added ? <span className="added-mark">В профилях</span> : (
        <Button small onClick={async () => {
          setSplit(await post("/api/split/profiles", { preset: p.id, route: p.default_route }));
          toast(`${p.name}: ${ROUTE_LABEL[p.default_route]}`);
        }}>{p.default_route === "direct" ? "Добавить напрямую" : "Добавить через запрет"}</Button>
      )}
    </div>
  );
}

export default function PresetCatalog() {
  const { presets } = useStore();
  return <div className="presets">{presets.map((p) => <Preset key={p.id} p={p} />)}</div>;
}
