// Playwright E2E — traceability fixture (DATA, not executed here).
// Demonstrates a native-tag e2e test that is enabled AND passing -> coverage ok.

import { test, expect } from '@playwright/test';

test('dashboard shows live orders', { tag: ['@FR-03.02'] }, async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByTestId('orders')).toBeVisible();
});
