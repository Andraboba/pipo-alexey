import { expect, test } from "@playwright/test";
import { mockApi, prepare } from "./mock.js";

const theme = (page) => page.evaluate(() => document.documentElement.dataset.theme);
const bg = (page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const DARK = "rgb(20, 20, 21)";
const LIGHT = "rgb(250, 250, 250)";

for (const scheme of ["dark", "light"]) {
  test(`по умолчанию тема как в системе: ${scheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await prepare(page);
    await mockApi(page);
    await page.goto("./#settings");
    await expect(page.getByRole("radio", { name: "Как в системе" })).toHaveAttribute("aria-checked", "true");
    expect(await theme(page)).toBe(scheme);
    expect(await bg(page)).toBe(scheme === "dark" ? DARK : LIGHT);
  });
}

test("«Как в системе» переключается вслед за Windows без перезапуска", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await prepare(page);
  await mockApi(page);
  await page.goto("./#panel");
  await page.locator(".engine").waitFor();
  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => theme(page)).toBe("light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => theme(page)).toBe("dark");
});

test("выбранная тема не зависит от системы и сохраняется", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await prepare(page);
  await mockApi(page);
  await page.goto("./#settings");
  await page.getByRole("radio", { name: "Светлая" }).click();
  expect(await theme(page)).toBe("light");
  expect(await bg(page)).toBe(LIGHT);
  await page.reload();
  await expect(page.getByRole("radio", { name: "Светлая" })).toHaveAttribute("aria-checked", "true");
  expect(await theme(page)).toBe("light");
  await page.emulateMedia({ colorScheme: "light" });
  await page.getByRole("radio", { name: "Тёмная" }).click();
  await page.emulateMedia({ colorScheme: "light" });
  expect(await theme(page)).toBe("dark");
  expect(await bg(page)).toBe(DARK);
});
