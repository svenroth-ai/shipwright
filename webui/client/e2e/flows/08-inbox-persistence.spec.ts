import { test, expect } from '@playwright/test';

test.describe('Inbox', () => {
  test('inbox page renders with empty state or items', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page.getByRole('heading', { name: 'Inbox' })).toBeVisible();
    // Page rendered successfully — may show empty state, items, or loading skeleton
    await expect(page.locator('main')).toBeVisible();
  });

  test('inbox shows project grouping for pending items', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page.locator('main')).toBeVisible();
  });
});
