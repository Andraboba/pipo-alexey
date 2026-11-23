import { cellState } from "./cellState.js";
import { ANY_CODE_NOTE, humanDetail } from "./humanDetail.js";

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
  const state = r ? cellState(r, meta) : "";
  // сравнение с прогоном без запрета: стратегия сломала открытую цель или починила заблокированную
  const verdict = !r || r === base || !meta ? null
    : meta.status === "open" && state !== "ok" ? { cls: "t-bad", text: "Без запрета проходит — эта стратегия ломает соединение" }
    : meta.status === "blocked" && state === "ok" ? { cls: "t-ok", text: "Без запрета не проходит — эта стратегия починила" }
    : null;
  const answered = t.kind === "url" && [r, base].some((x) => /TLS1\.\d \d{3}/.test(x?.detail || ""));
  const style = below ? { left, top: box.bottom + 8 } : { left, bottom: window.innerHeight - box.top + 8 };
  return (
    <div className="celltip" style={style} role="tooltip">
      <b>{t.name}</b>
      <div className="sub">{t.about || t.group}</div>
      <div className="mono tip-addr">{t.url || `${t.host}${t.port ? ":" + t.port : ""}`}</div>
      {r && <div className="tip-row"><i className={"cell " + state} /><span>{r === base ? "Без запрета" : "Здесь"}: {STATE[state]} · {humanDetail(r.detail)}</span></div>}
      {base && base !== r && <div className="tip-row"><i className={"cell " + cellState(base, meta)} /><span>Без запрета: {humanDetail(base.detail)}</span></div>}
      {verdict && <div className={"tip-verdict " + verdict.cls}>{verdict.text}</div>}
      {meta && <div className="tip-status">{STATUS[meta.status]}</div>}
      {answered && <div className="tip-note">{ANY_CODE_NOTE}</div>}
    </div>
  );
}
