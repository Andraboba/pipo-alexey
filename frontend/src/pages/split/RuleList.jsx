import { useState } from "react";
import { del, patch } from "../../lib/api.js";
import { COUNTRIES, fmt, nets } from "../../lib/format.js";
import { useStore } from "../../store.jsx";
import { Seg, useAction } from "../../ui/controls.jsx";
import { IconCheck, IconPause, IconPlay, IconTrash } from "../../ui/icons.jsx";
import { useToast } from "../../ui/Toasts.jsx";
import { checkHost } from "./checkHost.js";
import { ROUTES } from "./RuleForm.jsx";

const FILTERS = [{ v: "all", label: "Все" }, ...ROUTES];

function meta(r) {
  if (r.kind === "ip") return "IP";
  if (r.kind === "domain") return "домен";
  const n = `${fmt(r.size)} ${nets(r.size)}`;
  return r.route === "direct" && r.kept_blocked
    ? `${n} · ${r.kept_blocked} заблокированных из списка Flowseal остаются через запрет`
    : n;
}

function Rule({ r, onCheck }) {
  const { setSplit } = useStore();
  const act = useAction();
  const toast = useToast();
  const update = (body) => act(async () => setSplit(await patch(`/api/split/rules/${r.id}`, body)));
  return (
    <div className={"rule " + (r.enabled ? r.route : "off")}>
      <span className="bar" />
      <div className="val">
        {r.kind === "geo" ? <>GeoIP · {r.value}<span className="meta">{COUNTRIES[r.value]}</span></> : r.value}
        <span className="meta">{meta(r)}{r.note ? " · " + r.note : ""}{r.enabled ? "" : " · выключено"}</span>
      </div>
      <Seg small options={ROUTES} value={r.route} onChange={(route) => update({ route })} />
      <div className="tools">
        {r.kind === "domain" && (
          <button className="icon-btn" title="Проверить доступ" onClick={() => act(async () => onCheck(await checkHost(r.value)))}><IconCheck /></button>
        )}
        <button className="icon-btn" title={r.enabled ? "Выключить" : "Включить"} onClick={() => update({ enabled: !r.enabled })}>
          {r.enabled ? <IconPause /> : <IconPlay />}
        </button>
        <button className="icon-btn danger" title="Удалить" onClick={() => act(async () => {
          setSplit(await del(`/api/split/rules/${r.id}`));
          toast(`Удалено: ${r.value}`);
        })}><IconTrash /></button>
      </div>
    </div>
  );
}

export default function RuleList({ onCheck }) {
  const { split } = useStore();
  const [filter, setFilter] = useState("all");
  if (!split) return null;
  const rules = split.rules.filter((r) => filter === "all" || r.route === filter);
  return (
    <div className="card">
      <div className="list-head">
        <div className="card-title">Правила <span className="count">{split.rules.length || ""}</span></div>
        <Seg small options={FILTERS} value={filter} onChange={setFilter} />
      </div>
      <div className="rules">
        {rules.length ? rules.map((r) => <Rule key={r.id} r={r} onCheck={onCheck} />) : (
          <div className="empty">
            {split.rules.length ? "Под этот фильтр ничего не попадает" : "Правил пока нет. Добавьте незаблокированный сайт — и он пойдёт мимо запрета"}
          </div>
        )}
      </div>
    </div>
  );
}
