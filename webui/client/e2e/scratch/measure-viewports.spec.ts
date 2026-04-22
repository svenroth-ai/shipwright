import { test } from '@playwright/test';

for (const vw of [1200, 1400, 1600, 1800, 2000]) {
  test(`widths at ${vw}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width: vw, height: 900 });
    await page.goto('http://localhost:5173/projects');
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(300);
    const proj = await page.locator('.page-container').first().boundingBox();

    await page.goto('http://localhost:5173/');
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(300);
    const boardCols = await page.locator('[data-testid="task-board-columns"]').boundingBox();

    await page.goto('http://localhost:5173/?view=list');
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(300);
    const listPC = await page.locator('.page-container').last().boundingBox();

    console.log(`vw=${vw} projects:`, proj?.x, proj?.width, '| board cols:', boardCols?.x, boardCols?.width, '| list:', listPC?.x, listPC?.width);
  });
}
