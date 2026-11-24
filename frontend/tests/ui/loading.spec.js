import { expect, test } from "@playwright/test";
import { pathToFileURL } from "node:url";
import path from "node:path";

// Заглушка загрузки окна Tauri (desktop/loading): тему ей передаёт оболочка через window.__PIPO_THEME
const PAGE = pathToFileURL(path.resolve("../desktop/loading/index.html")).href;
const bg = (page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const DARK = "rgb(20, 20, 21)";
const LIGHT = "rgb(250, 250, 250)";

async function open(page, { saved, system }) {
  await page.emulateMedia({ colorScheme: system });
  if (saved) await page.addInitScript((t) => { window.__PIPO_THEME = t; }, saved);
  await page.goto(PAGE);
}

const cases = [
  { saved: "light", system: "dark", want: LIGHT },
  { saved: "dark", system: "light", want: DARK },
  { saved: "system", system: "light", want: LIGHT },
  { saved: "system", system: "dark", want: DARK },
  { saved: null, system: "light", want: LIGHT }, // старый settings.json без темы
];
for (const c of cases) {
  test(`заглушка: выбрано ${c.saved ?? "ничего"}, в Windows ${c.system}`, async ({ page }) => {
    await open(page, c);
    expect(await bg(page)).toBe(c.want);
    await expect(page.getByText("Запускаю…")).toBeVisible();
  });
}

test("ошибка запуска видна и в светлой теме", async ({ page }) => {
  await open(page, { saved: "light", system: "light" });
  await page.evaluate(() => window.showError("Сервер не ответил за 30 секунд", "data\\pipo.log"));
  await expect(page.getByText("Сервер не ответил за 30 секунд")).toBeVisible();
  const color = await page.locator("#error b").evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe("rgb(220, 38, 38)");
  expect(await bg(page)).toBe(LIGHT);
});
