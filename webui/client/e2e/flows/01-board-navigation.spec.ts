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

  test('create button is visible', async ({ page }) => {
    // Iterate 14.4 renamed the primary CTA from "New Task" to just "New"
    // (split-button CreateMenu — see e2e/flows/13-create-menu.spec.ts).
    await page.goto('/');
    await expect(page.getByRole('button', { name: /create new/i })).toBeVisible();
  });
});
