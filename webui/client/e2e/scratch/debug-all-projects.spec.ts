import { test, expect } from '@playwright/test';

test('debug — single project → All projects', async ({ page }) => {
  const consoleMsgs: string[] = [];
  page.on('console', (msg) => consoleMsgs.push(`[${msg.type()}] ${msg.text()}`));

  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle').catch(() => {});

  // 1. Open dropdown, click a concrete project
  await page.getByTestId('project-filter-dropdown').click();
  await page.waitForTimeout(200);

  // Find first project item (not "all", not "unassigned", not "new")
  const projectItems = page.locator('[data-testid^="project-filter-dropdown-item-"]');
  const count = await projectItems.count();
  console.log(`dropdown items: ${count}`);

  // Prefer a real project (not "all" / "unassigned") — pick the 2nd item
  const target = projectItems.nth(2);
  const targetTestId = await target.getAttribute('data-testid');
  const targetLabel = await target.textContent();
  console.log(`picking ${targetTestId}: ${targetLabel}`);

  await target.click();
  await page.waitForTimeout(1000);

  const urlAfterProject = page.url();
  const triggerLabelAfterProject = await page.getByTestId('project-filter-dropdown').textContent();
  console.log(`after single project: url=${urlAfterProject}, trigger=${triggerLabelAfterProject}`);

  // 2. Screenshot the state
  await page.screenshot({ path: 'e2e/screenshots/debug-all-projects-step1-single.png', fullPage: false });

  // 3. Click All Projects
  await page.getByTestId('project-filter-dropdown').click();
  await page.waitForTimeout(200);
  await page.getByTestId('project-filter-dropdown-item-all').click();
  await page.waitForTimeout(1500);

  const urlAfterAll = page.url();
  const triggerLabelAfterAll = await page.getByTestId('project-filter-dropdown').textContent();
  console.log(`after all: url=${urlAfterAll}, trigger=${triggerLabelAfterAll}`);

  await page.screenshot({ path: 'e2e/screenshots/debug-all-projects-step2-all.png', fullPage: false });

  const tbpDebug = await page.evaluate(() => (window as unknown as { __TBP_DEBUG__?: unknown }).__TBP_DEBUG__);
  console.log('TBP debug:', JSON.stringify(tbpDebug));

  // Assert: URL should not carry ?projectId, trigger should say "All projects"
  expect(urlAfterAll).not.toContain('projectId=');
  expect(triggerLabelAfterAll).toContain('All projects');

  console.log('console messages:');
  for (const m of consoleMsgs) console.log(m);
});
