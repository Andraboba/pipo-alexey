import { get, put } from "./api.js";

// Тема, масштаб и пройденный гайд живут в localStorage страницы, а он привязан к её адресу (порту)
// и к окну (у pywebview и Tauri разные профили). Копия — на сервере (/api/ui → data\settings.json).
// Правило: на сервер уходит только явный выбор пользователя; пустой localStorage берёт значение с сервера.

let fetched = null;
const serverPrefs = () => (fetched ??= get("/api/settings").catch(() => null));

/** Отправить выбор пользователя. Ошибка не критична: при следующем выборе уйдёт снова. */
export const pushPref = (patch) => put("/api/ui", patch).catch(() => {});

/** Если в localStorage[key] пусто — взять с сервера (serverKey), сохранить локально и применить.
 *  Возвращает промис: когда он выполнен, локальное значение уже окончательное. */
export function adoptPref(key, serverKey, toLocal, apply) {
  if (localStorage.getItem(key) !== null) return Promise.resolve();
  return serverPrefs().then((s) => {
    const v = toLocal(s?.[serverKey]);
    if (v !== null && localStorage.getItem(key) === null) {
      localStorage.setItem(key, v);
      apply(v);
    }
  });
}
