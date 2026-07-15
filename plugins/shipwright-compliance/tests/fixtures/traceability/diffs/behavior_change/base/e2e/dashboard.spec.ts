import { test, expect } from '@playwright/test';

test('dashboard shows live orders', { tag: ['@FR-03.02'] }, async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByTestId('orders')).toBeVisible();
});
