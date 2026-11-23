const Z_STATE = {
  running: ["Работает", "green"],
  stopped: ["Остановлен", ""],
  start_pending: ["Запускается…", "amber"],
  stop_pending: ["Останавливается…", "amber"],
  paused: ["Пауза", "amber"],
};

/** Человеческое состояние запрета: заголовок, подпись, цвет лампы. */
export function zapretView(z) {
  const on = z.service === "running" || z.winws_running;
  if (!z.exists) return { label: "Не найден", lamp: "red", sub: `В ${z.dir} нет bin\\${z.exe} — проверьте «Настройки» или установите его во вкладке «Обновления»`, on };
  if (z.service === null && z.winws_running) return { label: "Работает (.bat)", lamp: "green", sub: "winws запущен из .bat-файла, не как служба", on };
  if (z.service === null) return { label: "Служба не установлена", lamp: "", sub: "Выберите стратегию и нажмите «Установить службу»", on };
  const [label, lamp] = Z_STATE[z.service] || [z.service, ""];
  return { label, lamp, sub: `Стратегия: ${z.strategy || "—"}`, on };
}

export function tgView(tg) {
  if (!tg.installed) return { label: "Не установлен", lamp: "", sub: "Можно установить во вкладке «Обновления»", on: false };
  if (tg.running && tg.listening) return { label: "Работает", lamp: "green", sub: `Слушает ${tg.host}:${tg.port}`, on: true };
  if (tg.running) return { label: "Запускается…", lamp: "amber", sub: `Порт ${tg.port} пока не отвечает`, on: true };
  return { label: "Остановлен", lamp: "", sub: "Telegram с этим прокси подключаться не будет", on: false };
}
