import { test, expect } from '@playwright/test';

test.describe('Inbox', () => {
  test('navigates to inbox page', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page).toHaveURL('/inbox');
    // Inbox page should render (either with items or empty state)
    await expect(page.locator('main')).toBeVisible();
  });
});
