export default function StrategyPicker({ all, picked, setPicked, current, disabled }) {
  const toggle = (s) => {
    const next = new Set(picked);
    next.has(s) ? next.delete(s) : next.add(s);
    setPicked(next);
  };
  return (
    <div className="card">
      <div className="list-head" style={{ marginBottom: 8 }}>
        <div className="card-title">Стратегии <span className="count">{picked.size} из {all.length}</span></div>
        <div className="row">
          <button className="link" disabled={disabled} onClick={() => setPicked(new Set(all))}>Все</button>
          <button className="link" disabled={disabled} onClick={() => setPicked(new Set())}>Ни одной</button>
        </div>
      </div>
      <div className="chips">
        {all.map((s) => (
          <button key={s} type="button" disabled={disabled} className={"chip" + (picked.has(s) ? " on" : "")} onClick={() => toggle(s)}>
            {s.replace(/^general\s*\(?/, "").replace(/\)$/, "") || "general"}
            {s === current && <span className="cur">служба</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
