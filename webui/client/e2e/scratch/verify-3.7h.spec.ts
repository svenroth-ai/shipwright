import { test } from '@playwright/test';

test('3.7h verify — Board + List view + filter in list', async ({ page }) => {
  await page.setViewportSize({ width: 1720, height: 900 });
  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7h-board.png', fullPage: false });

  // Switch to List view via URL
  await page.goto('http://localhost:5173/?view=list');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);
  await page.screenshot({ path: 'e2e/screenshots/3.7h-list.png', fullPage: false });

  // Click a status chip to verify filter wiring in List view
  const chip = page.getByTestId('board-filter-status-draft');
  if (await chip.count() > 0) {
    await chip.click({ force: true }).catch(() => {});
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'e2e/screenshots/3.7h-list-filtered-draft.png', fullPage: false });
  }
});
