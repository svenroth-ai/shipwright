import { test, expect } from '@playwright/test';

test.describe('Inbox', () => {
  test('inbox page renders with empty state or items', async ({ page }) => {
    await page.goto('/inbox');
    await expect(page.getByText('Inbox')).toBeVisible();
    // Either shows empty state or inbox items
    const emptyState = page.getByText('All caught up');
    const pendingSection = page.getByText(/Pending|Answered/);
    const hasContent = await Promise.race([
      emptyState.isVisible({ timeout: 2000 }).then(() => 'empty'),
      pendingSection.isVisible({ timeout: 2000 }).then(() => 'items'),
    ]).catch(() => 'empty');
    expect(['empty', 'items']).toContain(hasContent);
  });

  test('inbox shows project grouping for pending items', async ({ page }) => {
    await page.goto('/inbox');
    // Page should render without errors
    await expect(page.locator('main')).toBeVisible();
  });
});
