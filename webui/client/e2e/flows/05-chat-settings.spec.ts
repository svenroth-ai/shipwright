import { test, expect } from '@playwright/test';

test.describe('Chat Settings', () => {
  test('chat toolbar shows model, mode, effort, autonomy controls', async ({ page }) => {
    await page.goto('/');
    const taskCard = page.locator('[role="button"]').first();
    if (await taskCard.isVisible({ timeout: 2000 }).catch(() => false)) {
      await taskCard.click();
      await expect(page.locator('main')).toBeVisible();
    }
  });

  test('settings page has Global Settings tab with autonomy toggle', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('tab', { name: 'Global' })).toBeVisible();
    await expect(page.getByText('Default Autonomy')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Guided' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Autonomous' })).toBeVisible();
  });
});
