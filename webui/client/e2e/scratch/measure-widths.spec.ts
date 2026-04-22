import { test } from '@playwright/test';

test('measure Projects + List view widths', async ({ page }) => {
  await page.setViewportSize({ width: 2560, height: 1000 });

  // Projects page
  await page.goto('http://localhost:5173/projects');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);

  const projectsPC = await page.locator('.page-container').first().boundingBox();
  const projectsTable = await page.locator('[data-testid="projects-table"]').boundingBox();
  console.log('Projects page-container:', projectsPC);
  console.log('Projects table:', projectsTable);

  await page.screenshot({ path: 'e2e/screenshots/measure-projects.png', fullPage: false });

  // Board view
  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(500);

  const boardHeader = await page.locator('[data-testid="task-board-header"]').boundingBox();
  const boardFilter = await page.locator('[data-testid="board-filter-status"]').boundingBox();
  const boardColumns = await page.locator('[data-testid="task-board-columns"]').boundingBox();
  const boardBacklog = await page.locator('[data-testid="column-draft"]').boundingBox();
  console.log('Board header:', boardHeader);
  console.log('Board filter label:', boardFilter);
  console.log('Board columns container:', boardColumns);
  console.log('Board backlog col:', boardBacklog);
  const filterBottom = boardFilter ? boardFilter.y + boardFilter.height : 0;
  const colsTop = boardColumns ? boardColumns.y : 0;
  const backlogTop = boardBacklog ? boardBacklog.y : 0;
  console.log(`filter-chip-bottom=${filterBottom}, cols-container-top=${colsTop}, backlog-col-top=${backlogTop}`);
  console.log(`gap filter→cols-container: ${colsTop - filterBottom}px`);
  console.log(`gap filter→backlog-col: ${backlogTop - filterBottom}px`);

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
