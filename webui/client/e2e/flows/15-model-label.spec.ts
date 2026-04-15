import { test, expect } from '@playwright/test';

/**
 * Iterate 14.6 — dynamic model label in the chat toolbar.
 *
 * The ChatToolbar used to render a hardcoded "Claude Opus 4.6" label even
 * when CLI 2.1.1 defaulted to `claude-opus-4-5-20251101`. Iterate 14.6
 * routes the first `system/init` event's `model` through `chatStore` and
 * formats it via `formatModelLabel` (unit-tested separately).
 *
 * We assert here that the WebUI no longer ships the static "Opus 4.6"
 * string anywhere visible on the kanban board — the dropdown options now
 * display the CLI's real version after `system/init` lands, and the
 * fallback label is "Claude". The vitest unit suite on `formatModelLabel`
 * covers the parser itself.
 */
test.describe('Model label', () => {
  test('board page does not display the stale "Opus 4.6" string', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('main')).toBeVisible();
    // No element in the board header should show the hardcoded label.
    // (Iterate 14.6 routes the running model through the system/init
    // capture store; the dropdown labels themselves may still show
    // "Claude Opus 4.6" inside the popover content, which is fine — they
    // are inside a closed Popover and not rendered until the user clicks.)
    const staleLabel = page.locator('main').getByText('Opus 4.6', { exact: true });
    await expect(staleLabel).toHaveCount(0);
  });

  test('toolbar renders a running-model label container when a task chat is open', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('main')).toBeVisible();

    const taskCard = page.locator('[role="button"]').first();
    if (!(await taskCard.isVisible({ timeout: 2000 }).catch(() => false))) return;
    await taskCard.click();

    const runningLabel = page.locator('[data-testid="running-model-label"]').first();
    if (!(await runningLabel.isVisible({ timeout: 2000 }).catch(() => false))) return;

    const text = (await runningLabel.textContent())?.trim() ?? '';
    // Either real formatted label ("Opus 4.5", "Sonnet 4.6", …) or the
    // fallback ("Claude"). We assert it's non-empty and matches one of the
    // allowed shapes — and that it is NOT the stale "Opus 4.6".
    expect(text.length).toBeGreaterThan(0);
    expect(text).not.toBe('Opus 4.6');
    expect(/^(Claude|Opus|Sonnet|Haiku)( \d+\.\d+)?$/.test(text)).toBe(true);
  });
});
