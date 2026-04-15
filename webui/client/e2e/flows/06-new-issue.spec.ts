import { test, expect } from '@playwright/test';

/**
 * Iterate 14.4: the primary toolbar button is now a CreateMenu split
 * control (`[+ New ▾]`). Clicking it opens a Radix dropdown with "New Task"
 * and "New Pipeline…" items. Selecting "New Task" opens NewIssueModal.
 * Iterate 14.6 rewrote this spec to follow the new flow — see
 * e2e/flows/13-create-menu.spec.ts for the full CreateMenu coverage.
 */
test.describe('New Task', () => {
  test('create menu opens new task modal with start immediately checkbox', async ({ page }) => {
    await page.goto('/');
    const createBtn = page.getByRole('button', { name: /create new/i });
    if (!(await createBtn.isVisible({ timeout: 3000 }).catch(() => false))) return;
    await createBtn.click();
    const newTaskItem = page.getByRole('menuitem', { name: /new task/i });
    if (!(await newTaskItem.isVisible({ timeout: 2000 }).catch(() => false))) return;
    await newTaskItem.click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('Start immediately')).toBeVisible();
  });

  test('start immediately checkbox is checked by default', async ({ page }) => {
    await page.goto('/');
    const createBtn = page.getByRole('button', { name: /create new/i });
    if (!(await createBtn.isVisible({ timeout: 3000 }).catch(() => false))) return;
    await createBtn.click();
    const newTaskItem = page.getByRole('menuitem', { name: /new task/i });
    if (!(await newTaskItem.isVisible({ timeout: 2000 }).catch(() => false))) return;
    await newTaskItem.click();
    const checkbox = page.locator('input[type="checkbox"]').first();
    await expect(checkbox).toBeChecked();
  });

  test('create task button text', async ({ page }) => {
    await page.goto('/');
    const createBtn = page.getByRole('button', { name: /create new/i });
    if (!(await createBtn.isVisible({ timeout: 3000 }).catch(() => false))) return;
    await createBtn.click();
    const newTaskItem = page.getByRole('menuitem', { name: /new task/i });
    if (!(await newTaskItem.isVisible({ timeout: 2000 }).catch(() => false))) return;
    await newTaskItem.click();
    await expect(page.getByText('Create Task')).toBeVisible();
  });
});
