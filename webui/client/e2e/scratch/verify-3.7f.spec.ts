import { test } from '@playwright/test';

test('3.7f live verify — Board wide + scenes', async ({ page }) => {
  await page.setViewportSize({ width: 1720, height: 900 });
  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7f-board-wide.png', fullPage: false });

  await page.goto('http://localhost:5173/inbox');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7f-inbox.png', fullPage: true });

  await page.goto('http://localhost:5173/projects');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.screenshot({ path: 'e2e/screenshots/3.7f-projects.png', fullPage: false });
});
