import { test } from '@playwright/test';

test('measure Projects + List view widths', async ({ page }) => {
  await page.setViewportSize({ width: 1720, height: 900 });

  // Projects page
  await page.goto('http://localhost:5173/projects');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);

  const projectsPC = await page.locator('.page-container').first().boundingBox();
  const projectsTable = await page.locator('[data-testid="projects-table"]').boundingBox();
  console.log('Projects page-container:', projectsPC);
  console.log('Projects table:', projectsTable);

  await page.screenshot({ path: 'e2e/screenshots/measure-projects.png', fullPage: false });

  // List view
  await page.goto('http://localhost:5173/?view=list');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);

  const listPC = await page.locator('.page-container').last().boundingBox();
  const listTable = await page.locator('[data-testid="task-list-table"]').boundingBox();
  console.log('List page-container (last):', listPC);
  console.log('List table:', listTable);

  await page.screenshot({ path: 'e2e/screenshots/measure-list.png', fullPage: false });
});
