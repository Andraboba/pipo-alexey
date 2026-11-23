import { useState } from "react";
import { domains } from "../../lib/format.js";

export default function SectionList({ sections, picked, setPicked }) {
  const [q, setQ] = useState("");
  const query = q.trim().toLowerCase();
  const visible = sections.filter((s) => !query || s.name.toLowerCase().includes(query) || s.domains.some((d) => d.includes(query)));
  const ai = visible.filter((s) => s.ai);
  const other = visible.filter((s) => !s.ai);

  const toggle = (name) => {
    const next = new Set(picked);
    next.has(name) ? next.delete(name) : next.add(name);
    setPicked(next);
  };

  const Group = ({ title, items }) => items.length > 0 && (
    <div className="svc-group">
      <div className="svc-group-title">{title} <span className="count">{items.length}</span></div>
      <div className="svc-grid">
        {items.map((s) => (
          <label key={s.name} className={"svc" + (picked.has(s.name) ? " on" : "")} title={s.domains.join("\n")}>
            <input type="checkbox" checked={picked.has(s.name)} onChange={() => toggle(s.name)} />
            <span className="svc-name">{s.name.replace(/\s+AI$/, "")}</span>
            <span className="svc-meta">{s.count} {domains(s.count)}</span>
          </label>
        ))}
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="list-head">
        <div className="card-title">Сервисы <span className="count">{sections.length}</span></div>
        <input className="svc-search" placeholder="Поиск: сервис или домен" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Group title="Нейросети" items={ai} />
      <Group title="Остальное" items={other} />
      {!visible.length && <div className="empty">Ничего не найдено</div>}
    </div>
  );
}
