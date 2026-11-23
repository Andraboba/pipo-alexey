import { cellState } from "./cellState.js";

const STATUS = {
  blocked: "Заблокирована: без запрета не проходит",
  open: "Открыта: проходит и без запрета",
  dead: "Не отвечает ни без запрета, ни с одной стратегией — это не блокировка (или её не пробивает ничто), в оценке не учитывается",
};
const STATE = { ok: "проходит", half: "частично", bad: "не проходит", dead: "не отвечает", "": "ещё не проверено" };

/** Всплывашка над клеткой: что за адрес, чей он и что с ним произошло. */
export default function CellTip({ tip }) {
  const { t, el, r, base, meta } = tip;
  const box = el.getBoundingClientRect();
  const left = Math.min(Math.max(8, box.left - 140), window.innerWidth - 336);
  const below = box.top < 220;
  const style = below ? { left, top: box.bottom + 8 } : { left, bottom: window.innerHeight - box.top + 8 };
  return (
    <div className="celltip" style={style} role="tooltip">
      <b>{t.name}</b>
      <div className="sub">{t.about || t.group}</div>
      <div className="mono tip-addr">{t.url || `${t.host}${t.port ? ":" + t.port : ""}`}</div>
      {r && <div className="tip-row"><i className={"cell " + cellState(r, meta)} /> Здесь: {STATE[cellState(r, meta)]} · <span className="mono">{r.detail}</span></div>}
      {base && base !== r && <div className="tip-row"><i className={"cell " + cellState(base, meta)} /> Без запрета: <span className="mono">{base.detail}</span></div>}
      {meta && <div className="tip-status">{STATUS[meta.status]}</div>}
    </div>
  );
}
