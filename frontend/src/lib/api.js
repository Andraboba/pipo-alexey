// Токен этого запуска сервер вставляет в <meta name="pipo-token">.
// В режиме разработки (vite dev) он берётся из VITE_PIPO_TOKEN.
const meta = document.querySelector('meta[name="pipo-token"]')?.content;
const TOKEN = meta && !meta.startsWith("__") ? meta : import.meta.env.VITE_PIPO_TOKEN || "";

export async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "X-Pipo-Token": TOKEN, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* пустой ответ */
  }
  if (!res.ok) {
    const d = data?.detail;
    const err = new Error((typeof d === "string" ? d : d && JSON.stringify(d)) || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const get = (path) => api("GET", path);
export const post = (path, body = {}) => api("POST", path, body);
export const put = (path, body) => api("PUT", path, body);
export const patch = (path, body) => api("PATCH", path, body);
export const del = (path) => api("DELETE", path);
