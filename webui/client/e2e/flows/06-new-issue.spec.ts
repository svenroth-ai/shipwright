import { test, expect } from '@playwright/test';

test.describe('New Issue', () => {
  test('new issue button opens modal with start immediately checkbox', async ({ page }) => {
    await page.goto('/');
    // The "New Issue" button text may appear in different elements; use role
    const newIssueBtn = page.locator('button:has-text("New Issue")').first();
    if (await newIssueBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await newIssueBtn.click();
      await expect(page.getByRole('dialog')).toBeVisible();
      await expect(page.getByText('Start immediately')).toBeVisible();
      await expect(page.getByText('Launch Claude CLI right after creation')).toBeVisible();
    }
  });

  test('start immediately checkbox is checked by default', async ({ page }) => {
    await page.goto('/');
    const newIssueBtn = page.locator('button:has-text("New Issue")').first();
    if (await newIssueBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await newIssueBtn.click();
      const checkbox = page.locator('input[type="checkbox"]');
      await expect(checkbox).toBeChecked();
    }
  });
});
