import { useSyncExternalStore } from "react";
import { put } from "./api.js";

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
const saved = localStorage.getItem(KEY);
let pref = THEME_OPTIONS.some((o) => o.v === saved) ? saved : "system";

export const resolvedTheme = () => (pref === "system" ? (media.matches ? "light" : "dark") : pref);

function apply() {
  document.documentElement.dataset.theme = resolvedTheme();
  listeners.forEach((l) => l());
}

/** Копия выбора на сервере (data\settings.json): окно-оболочка красит заглушку загрузки ещё до старта сервера. */
const saveForShell = () => put("/api/ui", { theme: pref }).catch(() => { /* не критично: заглушка будет как в системе */ });

export function setThemePref(p) {
  pref = p;
  localStorage.setItem(KEY, p);
  apply();
  saveForShell();
}

// сменили тему Windows — «как в системе» переключается сразу, без перезапуска
media.addEventListener("change", apply);
apply();
saveForShell(); // выбор, сделанный до появления этой копии, тоже должен дойти до оболочки

const subscribe = (l) => { listeners.add(l); return () => listeners.delete(l); };

/** [выбор пользователя, итоговая тема, setter] */
export function useTheme() {
  useSyncExternalStore(subscribe, () => pref + "|" + resolvedTheme());
  return [pref, resolvedTheme(), setThemePref];
}
