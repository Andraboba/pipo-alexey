import { expect, test } from "@playwright/test";
import { mockApi, prepare, zoomOf } from "./mock.js";

// localStorage привязан к адресу и окну; копия настроек — на сервере (/api/settings → ui_*)
const theme = (page) => page.evaluate(() => document.documentElement.dataset.theme);
const uiPuts = (calls) => calls.filter((c) => c === "PUT /api/ui");

test("новая страница (другой порт или окно) берёт тему, масштаб и гайд с сервера", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await prepare(page, { tourDone: false }); // localStorage пустой
  const { calls } = await mockApi(page, {});
  await page.route("**/api/settings", (r) => r.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ zapret_dir: "C:\Zapret", zapret2_dir: "C:\Zapret2", tg_exe: null, ui_theme: "light", ui_scale: "1.25", ui_tour_done: true }),
  }));
  await page.goto("./#panel");
  await page.locator(".engine").waitFor();
  await expect.poll(() => theme(page)).toBe("light");
  await expect.poll(() => zoomOf(page)).toBe(1.25);
  await page.waitForTimeout(500);
  await expect(page.locator(".tour-card")).toHaveCount(0); // пройденный гайд не всплывает снова
  expect(uiPuts(calls), "сохранённый выбор не затирается при загрузке").toEqual([]);
});

test("при загрузке ничего не уходит на сервер, уходит только выбор пользователя", async ({ page }) => {
  await prepare(page, { tourDone: false });
  const { calls, state } = await mockApi(page);
  await page.goto("./#settings");
  await expect(page.locator(".tour-card")).toBeVisible();
  expect(uiPuts(calls)).toEqual([]);
  await page.keyboard.press("Escape"); // гайд закрывается и уводит на «Пульт»
  await page.goto("./#settings");
  await page.getByRole("radio", { name: "Светлая" }).click();
  await page.getByRole("radio", { name: "110%" }).click();
  await expect.poll(() => uiPuts(calls).length).toBe(3);
  expect(state["/api/settings"]).toMatchObject({ ui_theme: "light", ui_scale: "1.1", ui_tour_done: true });
});

test("в окне Tauri тема от оболочки применяется сразу, до ответа сервера", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await prepare(page);
  await page.addInitScript(() => { window.__PIPO_THEME = "light"; });
  await mockApi(page);
  await page.route("**/api/settings", () => {}); // сервер молчит
  await page.goto("./?shell=tauri#panel");
  expect(await theme(page)).toBe("light");
});
