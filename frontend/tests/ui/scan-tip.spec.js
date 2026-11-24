import { expect, test } from "@playwright/test";
import fixtures from "./fixtures.json" with { type: "json" };
import { mockApi, prepare } from "./mock.js";

// Подсказка над клеткой результатов подбора стоит у своей клетки при любом масштабе интерфейса
for (const scale of ["1", "1.4"]) {
  test(`подсказка подбора у своей клетки, масштаб ${scale}`, async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await prepare(page, { scale });
    const targets = { ...fixtures["/api/scan/targets"], last: fixtures.scan_last };
    await mockApi(page, { "/api/scan/targets": targets });
    await page.goto("./#scan");
    const cells = page.locator(".cells .cell");
    await expect(cells.first()).toBeVisible();
    for (const cell of [cells.first(), cells.last()]) {
      await cell.scrollIntoViewIfNeeded();
      await cell.hover();
      const tip = page.locator(".celltip");
      await expect(tip).toBeVisible();
      const c = await cell.boundingBox();
      const t = await tip.boundingBox();
      const vp = page.viewportSize();
      // целиком в окне
      expect(t.x).toBeGreaterThanOrEqual(0);
      expect(t.x + t.width).toBeLessThanOrEqual(vp.width);
      expect(t.y).toBeGreaterThanOrEqual(0);
      expect(t.y + t.height).toBeLessThanOrEqual(vp.height);
      // по горизонтали накрывает клетку, по вертикали — сразу над ней или под ней
      expect(t.x).toBeLessThanOrEqual(c.x);
      expect(t.x + t.width).toBeGreaterThanOrEqual(c.x + c.width);
      const gap = t.y >= c.y + c.height ? t.y - (c.y + c.height) : c.y - (t.y + t.height);
      expect(gap, "зазор между клеткой и подсказкой").toBeGreaterThanOrEqual(0);
      expect(gap).toBeLessThan(20);
      await page.mouse.move(0, 0);
    }
  });
}
