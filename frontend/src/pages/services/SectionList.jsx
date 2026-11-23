import { useState } from "react";
import { domains } from "../../lib/format.js";

/** Вне SectionList: компонент, объявленный внутри, на каждом рендере новый — React пересоздаёт галочки и фокус слетает. */
function Group({ title, items, picked, toggle }) {
  if (!items.length) return null;
  return (
    <div className="svc-group">
      <div className="svc-group-title">{title} <span className="count">{items.length}</span></div>
      <div className="svc-grid">
        {items.map((s) => (
          <label key={s.name} className={"svc" + (picked.has(s.name) ? " on" : "")} title={tip(s.domains)}>
            <input type="checkbox" checked={picked.has(s.name)} onChange={() => toggle(s.name)} />
            <span className="svc-name">{s.name.replace(/\s+AI$/, "")}</span>
            <span className="svc-meta">{s.count} {domains(s.count)}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

const tip = (list) => list.slice(0, 8).join("\n") + (list.length > 8 ? `\n… и ещё ${list.length - 8}` : "");

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

  return (
    <div className="card">
      <div className="list-head">
        <div className="card-title">Сервисы <span className="count">{sections.length}</span></div>
        <input className="svc-search" aria-label="Поиск сервиса или домена" placeholder="Поиск: сервис или домен" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Group title="Нейросети" items={ai} picked={picked} toggle={toggle} />
      <Group title="Остальное" items={other} picked={picked} toggle={toggle} />
      {!visible.length && <div className="empty">Ничего не найдено</div>}
    </div>
  );
}
