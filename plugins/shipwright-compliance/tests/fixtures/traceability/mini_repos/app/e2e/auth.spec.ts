// Playwright E2E — traceability fixture (DATA, not executed here).
// Demonstrates the native-tag grammar form AND the R1 "skipped != covered" case:
// FR-03.01 requires e2e (explicit), but its only e2e test is skipped -> in the
// golden manifest coverage.e2e = "MISSING" (a present tag closes nothing).

import { test, expect } from '@playwright/test';

test.skip('signs in and lands on dashboard', { tag: ['@FR-03.01'] }, async ({ page }) => {
  await page.goto('/login');
  await expect(page).toHaveURL('/dashboard');
});
