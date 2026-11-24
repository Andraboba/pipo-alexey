import { expect, test } from "@playwright/test";
import { mockApi, prepare, zoomOf } from "./mock.js";

const box = (page, sel) => page.locator(sel).first().boundingBox();

test("масштаб сам не меняется от размера окна: по умолчанию 100%", async ({ page }) => {
  await prepare(page);
  await mockApi(page);
  for (const size of [{ width: 1360, height: 900 }, { width: 1920, height: 1080 }, { width: 2560, height: 1440 }]) {
    await page.setViewportSize(size);
    await page.goto("./#panel");
    await page.locator(".engine").waitFor();
    expect(await zoomOf(page), `окно ${size.width}×${size.height}`).toBe(1);
  }
});

test("старое значение «Авто» превращается в 100%", async ({ page }) => {
  await prepare(page, { scale: "auto" });
  await mockApi(page);
  await page.setViewportSize({ width: 2560, height: 1440 });
  await page.goto("./#settings");
  await expect(page.getByRole("radio", { name: "100%" })).toHaveAttribute("aria-checked", "true");
  expect(await zoomOf(page)).toBe(1);
});

test("масштаб выбирается в настройках и сохраняется", async ({ page }) => {
  await prepare(page);
  await mockApi(page);
  await page.goto("./#settings");
  await expect(page.getByRole("radio", { name: "Авто" })).toHaveCount(0);
  await page.getByRole("radio", { name: "125%" }).click();
  expect(await zoomOf(page)).toBe(1.25);
  await page.reload();
  await expect(page.getByRole("radio", { name: "125%" })).toHaveAttribute("aria-checked", "true");
  expect(await zoomOf(page)).toBe(1.25);
});

for (const size of [{ width: 1920, height: 1080 }, { width: 2560, height: 1440 }]) {
  test(`на весь экран ${size.width}×${size.height} контент по центру, а не у левого края`, async ({ page }) => {
    await page.setViewportSize(size);
    await prepare(page);
    await mockApi(page);
    await page.goto("./#panel");
    await page.locator(".engine").waitFor();
    const nav = await box(page, ".nav");
    const shell = await box(page, ".shell");
    const main = await box(page, "main");
    const left = main.x - (nav.x + nav.width);
    const right = shell.x + shell.width - (main.x + main.width);
    expect(left).toBeGreaterThan(40);
    expect(Math.abs(left - right), `поля слева ${left} и справа ${right}`).toBeLessThan(2);
  });
}

for (const scale of ["1", "1.4"]) {
  test(`масштаб ${scale}: без горизонтальной прокрутки, меню слева на всю высоту`, async ({ page }) => {
    await prepare(page, { scale });
    await mockApi(page);
    await page.goto("./#panel");
    await page.locator(".engine").waitFor();
    const vw = await page.evaluate(() => innerWidth);
    const vh = await page.evaluate(() => innerHeight);
    const shell = await box(page, ".shell");
    expect(shell.x + shell.width).toBeLessThanOrEqual(vw + 1);
    const nav = await box(page, ".nav");
    // высота меню считается от --vh: под zoom обычный vh вылез бы за окно
    expect(Math.abs(nav.y + nav.height - vh)).toBeLessThan(2);
  });
}

for (const scale of ["1", "1.4"]) {
  test(`с баннером сверху кнопка «Свернуть» видна, масштаб ${scale}`, async ({ page }) => {
    await prepare(page, { scale });
    const { state } = await mockApi(page);
    state["/api/status"].admin = false; // баннер «UI запущен без прав администратора»
    await page.goto("./#panel");
    await expect(page.locator(".banner.warn")).toBeVisible();
    const toggle = page.getByRole("button", { name: "Свернуть меню" });
    const vh = await page.evaluate(() => innerHeight);
    for (const y of [0, 2000]) {
      await page.evaluate((y) => scrollTo(0, y), y);
      const b = await toggle.boundingBox();
      expect(b.y + b.height, `прокрутка ${y}: низ кнопки в окне`).toBeLessThanOrEqual(vh);
      const nav = await page.locator(".nav").boundingBox();
      expect(Math.abs(nav.y + nav.height - vh), `прокрутка ${y}: меню до низа окна`).toBeLessThan(2);
    }
    await expect(page.locator(".banner.warn")).toBeInViewport(); // шапка с баннером закреплена
  });
}
