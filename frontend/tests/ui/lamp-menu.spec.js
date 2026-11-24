import { expect, test } from "@playwright/test";
import { mockApi, prepare } from "./mock.js";

const pill = (page, name) => page.locator(".lamp", { hasText: name });

/** Меню стоит под своей лампой: правые края совпадают, сверху небольшой зазор. */
async function expectUnder(page, lamp) {
  const menu = page.locator(".lamp-menu");
  await menu.evaluate((el) => Promise.all(el.getAnimations().map((a) => a.finished))); // меню въезжает снизу
  const p = await lamp.boundingBox();
  const m = await menu.boundingBox();
  expect(Math.abs(m.x + m.width - (p.x + p.width)), "правый край меню = правый край лампы").toBeLessThan(2);
  expect(m.y, "меню ниже лампы").toBeGreaterThanOrEqual(p.y + p.height);
  expect(m.y - (p.y + p.height), "и сразу под ней").toBeLessThan(16);
}

for (const scale of ["1", "1.25"]) {
  for (const size of [{ width: 1360, height: 900 }, { width: 2560, height: 1440 }]) {
    test(`меню под лампой: масштаб ${scale}, окно ${size.width}×${size.height}`, async ({ page }) => {
      await page.setViewportSize(size);
      await prepare(page, { scale });
      await mockApi(page);
      await page.goto("./#panel");
      for (const name of ["Запрет", "Прокси TG"]) {
        const lamp = pill(page, name);
        await lamp.click({ button: "right" });
        await expect(page.locator(".lamp-menu")).toBeVisible();
        await expectUnder(page, lamp);
        await page.keyboard.press("Escape");
        await expect(page.locator(".lamp-menu")).toHaveCount(0);
      }
    });
  }
}

test("меню под лампой, когда страница прокручена", async ({ page }) => {
  await prepare(page);
  await mockApi(page);
  await page.goto("./#panel");
  await page.locator(".routes").waitFor();
  await page.evaluate(() => scrollTo(0, 600));
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(0);
  const lamp = pill(page, "Запрет");
  await lamp.click({ button: "right" });
  await expectUnder(page, lamp);
});

test("ПКМ по запрету: запустить, не уходя с вкладки", async ({ page }) => {
  await prepare(page);
  const { calls } = await mockApi(page);
  await page.goto("./#split");
  await pill(page, "Запрет").click({ button: "right" });
  const menu = page.locator(".lamp-menu");
  await expect(menu.getByRole("menuitem", { name: "Запустить", exact: true })).toBeEnabled();
  await expect(menu.getByRole("menuitem", { name: "Остановить", exact: true })).toBeDisabled();
  await expect(menu.getByRole("menuitem", { name: "Перезапустить", exact: true })).toBeDisabled();
  await menu.getByRole("menuitem", { name: "Запустить", exact: true }).click();
  await expect(menu).toHaveCount(0);
  await expect(page.locator(".toast", { hasText: "Запрет запущен" })).toBeVisible();
  await expect(pill(page, "Запрет")).toContainText("вкл");
  expect(calls).toContain("POST /api/zapret/start");
  expect(page.url()).toContain("#split");
});

test("ПКМ по прокси TG: запустить и остановить", async ({ page }) => {
  await prepare(page);
  const { calls } = await mockApi(page);
  await page.goto("./#panel");
  const lamp = pill(page, "Прокси TG");
  await lamp.click({ button: "right" });
  await page.locator(".lamp-menu").getByRole("menuitem", { name: "Запустить", exact: true }).click();
  await expect(lamp).toContainText("вкл");
  await lamp.click({ button: "right" });
  await page.locator(".lamp-menu").getByRole("menuitem", { name: "Остановить", exact: true }).click();
  await expect(lamp).toContainText("выкл");
  expect(calls).toEqual(["POST /api/tg/start", "POST /api/tg/stop"]);
});

test("служба не установлена — запуск недоступен и есть подсказка", async ({ page }) => {
  await prepare(page);
  const { state } = await mockApi(page);
  state["/api/status"].zapret.service = null;
  await page.goto("./#panel");
  await pill(page, "Запрет").click({ button: "right" });
  const menu = page.locator(".lamp-menu");
  await expect(menu.getByRole("menuitem", { name: "Запустить", exact: true })).toBeDisabled();
  await expect(menu).toContainText("Служба не установлена");
});

test("клик по лампе открывает вкладку, клик мимо меню закрывает его", async ({ page }) => {
  await prepare(page);
  await mockApi(page);
  await page.goto("./#panel");
  await pill(page, "Прокси TG").click();
  await expect(page).toHaveURL(/#telegram$/);
  await pill(page, "Запрет").click({ button: "right" });
  await page.locator("main").click({ position: { x: 5, y: 5 } });
  await expect(page.locator(".lamp-menu")).toHaveCount(0);
  await pill(page, "Запрет").click({ button: "right" });
  await page.locator(".lamp-menu").getByRole("menuitem", { name: /Открыть вкладку/ }).click();
  await expect(page).toHaveURL(/#panel$/);
});
