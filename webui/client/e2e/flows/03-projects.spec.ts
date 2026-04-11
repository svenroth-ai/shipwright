import { test, expect } from '@playwright/test';

test.describe('Projects', () => {
  test('navigates to projects page', async ({ page }) => {
    await page.goto('/projects');
    await expect(page).toHaveURL('/projects');
    await expect(page.locator('main')).toBeVisible();
  });
});
