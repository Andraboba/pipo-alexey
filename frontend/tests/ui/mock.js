import fixtures from "./fixtures.json" with { type: "json" };

const clone = (v) => JSON.parse(JSON.stringify(v));

/** Подменить API: GET — из фикстур (overrides поверх), POST/PUT — запомнить и ответить как сервер.
 *  Возвращает { calls, state }: calls — список «METHOD /path», state — текущие ответы. */
export async function mockApi(page, overrides = {}) {
  const state = { ...clone(fixtures), ...clone(overrides) };
  const calls = [];
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const method = req.method();
    if (method !== "GET") calls.push(`${method} ${path}`);
    const st = state["/api/status"];
    const reply = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (method === "GET") {
      return path in state ? reply(state[path]) : reply({ detail: `нет фикстуры для ${path}` }, 404);
    }
    switch (path) {
      case "/api/zapret/start":
      case "/api/zapret/restart":
        st.zapret.service = "running";
        return reply(st.zapret);
      case "/api/zapret/stop":
        st.zapret.service = "stopped";
        return reply(st.zapret);
      case "/api/tg/start":
        Object.assign(st.tg, { running: true, listening: true });
        return reply(st.tg);
      case "/api/ui": {
        const keys = { theme: "ui_theme", scale: "ui_scale", tour_done: "ui_tour_done" };
        for (const [k, v] of Object.entries(req.postDataJSON())) state["/api/settings"][keys[k]] = v;
        return reply({ ok: true });
      }
      case "/api/tg/stop":
        Object.assign(st.tg, { running: false, listening: false });
        return reply(st.tg);
      default:
        return reply({ ok: true });
    }
  });
  return { calls, state };
}

/** Состояние для теста: гайд уже пройден (если не сказано иное), масштаб — как задан. */
export async function prepare(page, { tourDone = true, scale } = {}) {
  await page.addInitScript(({ tourDone, scale }) => {
    if (sessionStorage.getItem("__prepared")) return; // только при первой загрузке — reload сохраняет выбор
    sessionStorage.setItem("__prepared", "1");
    localStorage.clear();
    if (tourDone) localStorage.setItem("tourDone", "1");
    if (scale) localStorage.setItem("uiScale", scale);
  }, { tourDone, scale });
}

export const zoomOf = (page) => page.evaluate(() => Number(document.documentElement.style.zoom || 1));
