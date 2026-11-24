import { useSyncExternalStore } from "react";

// Масштаб интерфейса: на большом окне (полный экран 1080p, 2K) всё крупнее, чтобы не было
// мелкого текста посреди пустого поля. «Авто» считается от ширины окна, остальные — вручную.
const KEY = "uiScale";

export const SCALE_OPTIONS = [
  { v: "auto", label: "Авто" },
  { v: "0.9", label: "90%" },
  { v: "1", label: "100%" },
  { v: "1.1", label: "110%" },
  { v: "1.25", label: "125%" },
  { v: "1.4", label: "140%" },
];

/** Ширина окна в CSS-пикселях → масштаб. Окно по умолчанию (1360) остаётся как было. */
export function autoScale(width) {
  if (width < 1600) return 1;
  if (width < 2000) return 1.1;
  if (width < 2400) return 1.2;
  return 1.3;
}

const listeners = new Set();
let pref = localStorage.getItem(KEY) || "auto";

export function effectiveScale(p = pref) {
  return p === "auto" ? autoScale(window.innerWidth) : Number(p) || 1;
}

function apply() {
  const z = effectiveScale();
  document.documentElement.style.zoom = z === 1 ? "" : String(z);
  // vh внутри zoom увеличивается вместе с ним — высоту окна считаем сами
  document.documentElement.style.setProperty("--vh", window.innerHeight / z / 100 + "px");
  listeners.forEach((l) => l());
}

export function setScalePref(p) {
  pref = p;
  localStorage.setItem(KEY, p);
  apply();
}

window.addEventListener("resize", apply);
apply();

const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };
const snapshot = () => pref + "|" + effectiveScale();

/** [выбор пользователя, фактический масштаб, setter] */
export function useUiScale() {
  useSyncExternalStore(subscribe, snapshot);
  return [pref, effectiveScale(), setScalePref];
}

/** getBoundingClientRect в координатах внутри масштабированной страницы (для position: fixed). */
export function cssRect(el) {
  const z = effectiveScale();
  const r = el.getBoundingClientRect();
  return { left: r.left / z, top: r.top / z, right: r.right / z, bottom: r.bottom / z, width: r.width / z, height: r.height / z };
}

/** Размер окна в тех же координатах. */
export function cssViewport() {
  return { width: document.documentElement.clientWidth, height: window.innerHeight / effectiveScale() };
}
