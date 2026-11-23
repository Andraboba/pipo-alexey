/** Текст окна подтверждения: что именно произойдёт при обновлении. */
export function confirmText(target, d, status) {
  if (target === "zapret") {
    const running = status?.zapret.service === "running";
    return {
      title: d.newer ? `Обновить запрет ${d.local} → ${d.latest}?` : `Переустановить запрет ${d.latest || ""}?`,
      ok: "Скачать и установить",
      body: (
        <>
          {!d.newer && <p>У вас уже последняя версия — файлы будут перезаписаны той же версией.</p>}
          <ul>
            <li>Скачаю релиз с GitHub и проверю sha256.</li>
            <li>Остановлю запрет и драйвер WinDivert, сохраню бэкап заменяемых файлов в <code>data\backups</code>.</li>
            <li><b>Не трогаю</b>: ваши <code>*-user.txt</code>, <code>ipset-all.txt</code>, игровые профили и настройки игрового фильтра.</li>
            <li>Служба останется с той же стратегией{running ? " и запустится снова" : <> и <b>не будет запущена</b>, как и сейчас</>}.</li>
          </ul>
        </>
      ),
    };
  }
  if (target === "tg") {
    return {
      title: d.installed
        ? d.newer ? `Обновить TG WS Proxy ${d.local} → ${d.latest}?` : `Переустановить TG WS Proxy ${d.latest || ""}?`
        : `Установить TG WS Proxy ${d.latest || ""}?`,
      ok: "Скачать и установить",
      body: (
        <ul>
          <li>Скачаю <code>TgWsProxy_windows.exe</code> с GitHub (Flowseal/tg-ws-proxy) и проверю sha256.</li>
          <li>{d.installed ? <>Остановлю прокси, старый exe сохраню в <code>data\backups</code>.</> : "Положу его в папку запрета."}</li>
          <li>Конфиг и secret в <code>%APPDATA%\TgWsProxy</code> не меняются — Telegram переподключать не нужно.</li>
        </ul>
      ),
    };
  }
  return {
    title: "Обновить списки?",
    ok: "Обновить",
    body: <>Скачаю свежий <code>ipset-service.txt</code> от Flowseal, диапазоны стран из GeoIP-правил и префиксы ASN игр из RIPEstat. Ваши правила и профили наложатся поверх.</>,
  };
}
