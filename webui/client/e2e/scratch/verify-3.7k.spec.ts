import { test } from '@playwright/test';

test('3.7k verify — top padding + button parity + Diagnostics', async ({ page }) => {
  await page.setViewportSize({ width: 1720, height: 900 });

  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7k-board.png', fullPage: false });

  await page.goto('http://localhost:5173/?view=list');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7k-list.png', fullPage: false });

  await page.goto('http://localhost:5173/projects');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7k-projects.png', fullPage: false });

  await page.goto('http://localhost:5173/diagnostics');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7k-diagnostics.png', fullPage: true });
});
