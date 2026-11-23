const KIND = { url: "сайт", ip: "IP", dpi: "16–20 КБ" };

export default function TargetPicker({ targets, picked, setPicked, disabled }) {
  const groups = [];
  for (const t of targets) {
    let g = groups.find((x) => x.name === t.group);
    if (!g) groups.push((g = { name: t.group, items: [] }));
    g.items.push(t);
  }
  const toggle = (ids, on) => {
    const next = new Set(picked);
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
    setPicked(next);
  };

  return (
    <div className="card targets">
      <div className="card-title">Цели <span className="count">{picked.size}</span></div>
      <p className="hint">Список Flowseal (utils\targets.txt) и ваши игровые профили — домены и адреса из их сетей</p>
      {groups.map((g) => {
        const ids = g.items.map((t) => t.id);
        const all = ids.every((id) => picked.has(id));
        const some = !all && ids.some((id) => picked.has(id));
        return (
          <fieldset key={g.name} className="tgroup" disabled={disabled}>
            <label className="tgroup-head">
              <input type="checkbox" checked={all} ref={(el) => el && (el.indeterminate = some)} onChange={(e) => toggle(ids, e.target.checked)} />
              <b>{g.name}</b>
            </label>
            <div className="titems">
              {g.items.map((t) => (
                <label key={t.id} className="titem" title={t.url || t.host}>
                  <input type="checkbox" checked={picked.has(t.id)} onChange={(e) => toggle([t.id], e.target.checked)} />
                  <span>{t.name}</span>
                  <span className="kind">{KIND[t.kind]}</span>
                </label>
              ))}
            </div>
          </fieldset>
        );
      })}
    </div>
  );
}
