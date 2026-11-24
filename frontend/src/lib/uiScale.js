import { useSyncExternalStore } from "react";
import { adoptPref, pushPref } from "./uiPrefs.js";

// Масштаб интерфейса задаёт пользователь в «Настройках»: от размера окна и монитора он не зависит
// (системный масштаб Windows и так уже учтён). По умолчанию — 100%.
const KEY = "uiScale";

export const SCALE_OPTIONS = [
  { v: "0.9", label: "90%" },
  { v: "1", label: "100%" },
  { v: "1.1", label: "110%" },
  { v: "1.25", label: "125%" },
  { v: "1.4", label: "140%" },
];

const listeners = new Set();
// «auto» осталось от прошлой версии — теперь это просто 100%
const saved = localStorage.getItem(KEY);
let pref = SCALE_OPTIONS.some((o) => o.v === saved) ? saved : "1";

export function effectiveScale(p = pref) {
  return Number(p) || 1;
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
  pushPref({ scale: p });
}

// при изменении размера окна пересчитывается только --vh, сам масштаб тот же
window.addEventListener("resize", apply);
apply();
adoptPref(KEY, "ui_scale", (v) => (SCALE_OPTIONS.some((o) => o.v === v) ? v : null), (v) => { pref = v; apply(); });

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

let viewportProbe = null;

/** Размер окна (без полосы прокрутки) в тех же координатах. clientWidth под zoom не годится:
 *  он не масштабируется, а getBoundingClientRect — масштабируется. Поэтому меряем так же, как элементы. */
export function cssViewport() {
  if (!viewportProbe?.isConnected) {
    viewportProbe = document.createElement("div");
    viewportProbe.style.cssText = "position:fixed;inset:0;visibility:hidden;pointer-events:none";
    viewportProbe.setAttribute("aria-hidden", "true");
    document.body.appendChild(viewportProbe);
  }
  const z = effectiveScale();
  const r = viewportProbe.getBoundingClientRect();
  return { width: r.width / z, height: r.height / z };
}
