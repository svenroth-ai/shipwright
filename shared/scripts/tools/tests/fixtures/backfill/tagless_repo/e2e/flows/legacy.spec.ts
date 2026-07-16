// Playwright E2E — backfill fixture (DATA, not executed here).
// The orphan: FR-05.09 was moved to "## Removed Requirements" but this spec
// still carries the explicit @FR-05.09 tag → confirmed_orphan (reason
// fr_removed). The engine surfaces it; it NEVER deletes it.

import { test, expect } from '@playwright/test';

test('copies the launch command to the clipboard', { tag: ['@FR-05.09'] }, async ({ page }) => {
  await page.goto('/campaigns');
  await expect(page.getByRole('button', { name: 'Copy' })).toBeVisible();
});
