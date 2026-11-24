import { useSyncExternalStore } from "react";
import { adoptPref, pushPref } from "./uiPrefs.js";

// Тема: как в системе (по умолчанию), тёмная или светлая. На <html> всегда стоит итоговая
// data-theme="dark" | "light" — светлая палитра в tokens.css описана один раз.
const KEY = "theme";

export const THEME_OPTIONS = [
  { v: "system", label: "Как в системе" },
  { v: "dark", label: "Тёмная" },
  { v: "light", label: "Светлая" },
];

const media = window.matchMedia("(prefers-color-scheme: light)");
const listeners = new Set();
const valid = (v) => THEME_OPTIONS.some((o) => o.v === v);
// в окне Tauri тему из data\settings.json оболочка передаёт ещё до загрузки — без мигания
const saved = localStorage.getItem(KEY);
let pref = valid(saved) ? saved : valid(window.__PIPO_THEME) ? window.__PIPO_THEME : "system";

export const resolvedTheme = () => (pref === "system" ? (media.matches ? "light" : "dark") : pref);

function apply() {
  document.documentElement.dataset.theme = resolvedTheme();
  listeners.forEach((l) => l());
}

export function setThemePref(p) {
  pref = p;
  localStorage.setItem(KEY, p);
  apply();
  pushPref({ theme: p }); // копия для заглушки оболочки и для страницы на другом адресе
}

// сменили тему Windows — «как в системе» переключается сразу, без перезапуска
media.addEventListener("change", apply);
apply();
adoptPref(KEY, "ui_theme", (v) => (valid(v) ? v : null), (v) => { pref = v; apply(); });

const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };

/** [выбор пользователя, итоговая тема, setter] */
export function useTheme() {
  useSyncExternalStore(subscribe, () => pref + "|" + resolvedTheme());
  return [pref, resolvedTheme(), setThemePref];
}
