// Playwright E2E — backfill fixture (DATA, not executed here).
// The FILENAME carries the canonical FR-05.02 token → a deterministic
// path_fr_token match → the engine auto-writes a covers-comment above the
// test. Starts untagged.

import { test, expect } from '@playwright/test';

test('shows the live order feed', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(page.getByTestId('orders')).toBeVisible();
});
