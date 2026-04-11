import { test, expect } from '@playwright/test';

test.describe('Settings', () => {
  test('navigates to settings page', async ({ page }) => {
    await page.goto('/settings');
    await expect(page).toHaveURL('/settings');
    await expect(page.locator('main')).toBeVisible();
  });
});
