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

  test('new task button is visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('New Task')).toBeVisible();
  });
});
