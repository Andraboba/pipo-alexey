/** Цвет клетки: серый — цель мёртвая везде (не учитывается), иначе доля от «потолка» цели. */
export function cellState(r, meta) {
  if (meta?.status === "dead") return "dead";
  if (!r) return "";
  const cap = meta?.cap || 1;
  const part = r.score / cap;
  return part >= 1 ? "ok" : part > 0 ? "half" : "bad";
}
