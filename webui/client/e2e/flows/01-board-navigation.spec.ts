import { test, expect } from '@playwright/test';

test.describe('Board Navigation', () => {
  test('loads kanban board at root route', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('navigation')).toBeVisible();
    await expect(page.locator('main')).toBeVisible();
  });

  test('sidebar navigation links are visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: /board/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /inbox/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /projects/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /settings/i })).toBeVisible();
  });

  test('create-task split-button is visible', async ({ page }) => {
    // Iterate 3 section 03 — the inline form was replaced by the
    // `+ New ▾` split-button + NewIssueModal. The primary sub-button
    // is the discoverable entry point.
    await page.goto('/');
    await expect(page.getByTestId('create-menu-primary')).toBeVisible();
  });
});
