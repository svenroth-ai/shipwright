// Playwright E2E — traceability fixture (DATA, not executed here).
// The orphan: FR-03.09 was moved to "## Removed Requirements", but this spec
// still exists and still carries the tag -> confirmed_orphan (reason fr_removed).
// This is exactly the class of stale spec the campaign exists to catch.

import { test, expect } from '@playwright/test';

test('copies the launch command to the clipboard', { tag: ['@FR-03.09'] }, async ({ page }) => {
  await page.goto('/campaigns');
  await expect(page.getByRole('button', { name: 'Copy' })).toBeVisible();
});
