import { expect, test } from "@playwright/test";
import { mockApi, prepare } from "./mock.js";

const card = (page) => page.locator(".tour-card");
const next = (page) => card(page).getByRole("button", { name: /^(Показать|Дальше|Начать)$/ });
const stepText = async (page) => (await card(page).locator(".tour-step").textContent()).trim();

/** Карточка целиком в окне. */
async function expectCardInView(page) {
  const b = await card(page).boundingBox();
  const vp = page.viewportSize();
  expect(b.x).toBeGreaterThanOrEqual(0);
  expect(b.y).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width).toBeLessThanOrEqual(vp.width);
  expect(b.y + b.height).toBeLessThanOrEqual(vp.height);
}

/** Последняя рамка подсветки обводит главный элемент шага (с отступом). */
async function expectRingAround(page, selector) {
  const ring = page.locator(".tour-ring").last();
  const target = page.locator(selector).first();
  await expect.poll(async () => {
    const r = await ring.boundingBox();
    const t = await target.boundingBox();
    if (!r || !t) return false;
    return r.x <= t.x && r.y <= t.y && r.x + r.width >= t.x + t.width && r.y + r.height >= t.y + t.height
      && t.x - r.x < 12 && t.y - r.y < 12;
  }, { message: `подсветка вокруг ${selector}` }).toBe(true);
}

test("первый запуск: гайд открывается сам и проходит по вкладкам", async ({ page }) => {
  await prepare(page, { tourDone: false });
  await mockApi(page);
  await page.goto("./#panel");
  await expect(card(page)).toBeVisible();
  expect(await stepText(page)).toBe("1 из 13");
  await expect(page.getByText("Значок в трее")).toHaveCount(0); // в браузере трея нет

  const expected = [
    ["#panel", '[data-tour="engine"]'],
    ["#panel", '[data-tour="routes"]'],
    [null, '[data-tour="lamps"]'],
    ["#scan", "main .intro"],
    ["#telegram", '[data-tour="tg"]'],
    ["#services", "main .intro"],
    ["#games", "main .intro"],
    ["#split", "main .intro"],
    ["#diag", "main .intro"],
    ["#evolve", "main .intro"],
    ["#updates", "main .list-head"],
    ["#settings", '[data-tour="tour"]'],
  ];
  for (const [i, [hash, target]] of expected.entries()) {
    await next(page).click();
    await expect(card(page).locator(".tour-step")).toHaveText(`${i + 2} из 13`);
    if (hash) await expect(page).toHaveURL(new RegExp(hash + "$"));
    await expectRingAround(page, target);
    await expectCardInView(page);
  }
  await next(page).click(); // «Начать»
  await expect(card(page)).toHaveCount(0);
  await expect(page).toHaveURL(/#panel$/);
  await page.reload();
  await page.locator(".engine").waitFor();
  await expect(card(page)).toHaveCount(0);
});

test("в окне с треем гайд рассказывает про трей", async ({ page }) => {
  await prepare(page, { tourDone: false });
  await mockApi(page);
  await page.goto("./?shell=tauri#panel");
  expect(await stepText(page)).toBe("1 из 14");
  await page.keyboard.press("ArrowLeft"); // на первом шаге назад некуда
  for (let i = 0; i < 12; i++) await page.keyboard.press("ArrowRight");
  await expect(card(page)).toContainText("Значок в трее");
});

test("Esc пропускает гайд, из настроек его можно пройти снова", async ({ page }) => {
  await prepare(page, { tourDone: false });
  await mockApi(page);
  await page.goto("./#panel");
  await expect(card(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(card(page)).toHaveCount(0);
  await page.goto("./#settings");
  await page.getByRole("button", { name: "Пройти гайд ещё раз" }).click();
  await expect(card(page)).toBeVisible();
  expect(await stepText(page)).toBe("1 из 13");
});

for (const scale of ["1.25", "1.4"]) {
  test(`подсветка точная при масштабе ${scale}`, async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await prepare(page, { tourDone: false, scale });
    await mockApi(page);
    await page.goto("./#panel");
    await next(page).click();
    await expectRingAround(page, '[data-tour="engine"]');
    await expectCardInView(page);
    // затемнение покрывает окно целиком, но не больше
    const dim = await page.locator(".tour-dim").boundingBox();
    expect(Math.abs(dim.width - 1920)).toBeLessThan(20); // минус полоса прокрутки
    expect(Math.abs(dim.height - 1080)).toBeLessThan(2);
    await next(page).click();
    await next(page).click();
    await expectRingAround(page, '[data-tour="lamps"]');
    await expectCardInView(page);
  });
}
