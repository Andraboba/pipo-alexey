// Сырые итоги проверок из app/scan.py («TLS1.2 404; TLS1.3 ошибка 28») — в понятный текст.
// Работает и для результатов, сохранённых раньше: формат строки на сервере не менялся.

// коды выхода curl, которые встречаются при блокировках и поломках соединения
const CURL = {
  6: "адрес не найден в DNS",
  7: "сервер не принял подключение",
  28: "нет ответа, вышло время",
  35: "обрыв на TLS-рукопожатии",
  52: "сервер закрыл соединение без ответа",
  56: "соединение сброшено",
};

const curlError = (code) => `${CURL[code] || "ошибка соединения"} (код ${code})`;

/** Одна часть проверки сайта: «404», «ошибка 28», «подмена сертификата», «не поддерживается». */
function part(s) {
  if (/^\d{3}$/.test(s)) return `сервер ответил ${s}`;
  const err = s.match(/^ошибка (\d+)$/);
  if (err) return curlError(+err[1]);
  if (s === "не поддерживается") return "клиент не поддерживает";
  return s;
}

const FREEZE = /^заморозка: отправлено (\d+) КБ, ответа нет$/;

export function humanDetail(detail) {
  if (!detail) return "";
  // сайт: «TLS1.2 <итог>; TLS1.3 <итог>[; заморозка: …]»
  const chunks = detail.split(";").map((s) => s.trim());
  const tls = chunks.map((c) => c.match(/^TLS1\.(\d) (.+)$/)).filter(Boolean).map((m) => ({ v: m[1], text: part(m[2]) }));
  if (tls.length) {
    const head = tls.length === 2 && tls[0].text === tls[1].text
      ? `TLS 1.2 и 1.3: ${tls[0].text}`
      : tls.map((x) => `TLS 1.${x.v}: ${x.text}`).join(" · ");
    const freeze = chunks.map((c) => c.match(FREEZE)).find(Boolean);
    return freeze ? `${head}, но соединение замерзло: ${freeze[1]} КБ ушли, ответа нет` : head;
  }
  // тест на заморозку 16–20 КБ и прочее
  const err = detail.match(/^ошибка (\d+)$/);
  if (err) return curlError(+err[1]);
  return detail.replace(/^HTTP (\d{3})/, "сервер ответил $1");
}

/** Любой HTTP-код — соединение дошло до настоящего сервера (сертификат проверен). */
export const ANY_CODE_NOTE = "Код ответа (200, 403, 404…) выбирает сам сервер: раз он ответил с настоящим сертификатом, соединение не заблокировано";
