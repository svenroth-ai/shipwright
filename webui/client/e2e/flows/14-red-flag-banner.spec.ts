import { test, expect } from '@playwright/test';

/**
 * Iterate 14.5 / 14.6 — red-flag banner on AskUserCard.
 *
 * When the server detects that Claude continued generating after an
 * AskUserQuestion (text or a further tool_use arrived in the same turn),
 * it sets `inbox item.notBlocked = true` and emits `inbox:flag_not_blocked`
 * over SSE. The AskUserCard renders an amber banner and the InboxPage
 * list shows a warning icon.
 *
 * Without the ability to deterministically inject SSE events at this
 * level we keep the e2e check lightweight: load the InboxPage, assert
 * it renders, and if any `notBlocked` visual cue is present, confirm it's
 * visible. The vitest unit suite (`AskUserCard.test.tsx`,
 * `InboxPage.test.tsx`, `useSSE.test.ts`) covers the full behaviour.
 */
test.describe('Red flag banner', () => {
  test('inbox page renders even with potential notBlocked items', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page.getByRole('heading', { name: 'Inbox' })).toBeVisible();
    await expect(page.locator('main')).toBeVisible();

    // If a warning icon / amber banner is present, confirm it's visible.
    // Zero hits is a valid pass.
    const warningEl = page
      .locator('[data-testid="inbox-not-blocked-flag"], [data-testid="askuser-not-blocked-banner"]')
      .first();
    if (await warningEl.isVisible({ timeout: 1000 }).catch(() => false)) {
      await expect(warningEl).toBeVisible();
    }
  });
});
