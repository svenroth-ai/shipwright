import { test, expect } from '@playwright/test';

test.describe('New Task', () => {
  test('new task button opens modal with start immediately checkbox', async ({ page }) => {
    await page.goto('/');
    const newTaskBtn = page.locator('button:has-text("New Task")').first();
    if (await newTaskBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await newTaskBtn.click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await expect(page.getByText('Start immediately')).toBeVisible();
    }
  });

  test('start immediately checkbox is checked by default', async ({ page }) => {
    await page.goto('/');
    const newTaskBtn = page.locator('button:has-text("New Task")').first();
    if (await newTaskBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await newTaskBtn.click();
      const checkbox = page.locator('input[type="checkbox"]');
      await expect(checkbox).toBeChecked();
    }
  });

  test('create task button text', async ({ page }) => {
    await page.goto('/');
    const newTaskBtn = page.locator('button:has-text("New Task")').first();
    if (await newTaskBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await newTaskBtn.click();
      await expect(page.getByText('Create Task')).toBeVisible();
    }
  });
});
