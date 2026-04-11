import { test, expect } from '@playwright/test';

test.describe('Settings Persistence', () => {
  test('settings page has three tabs', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('tab', { name: 'Global Settings' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Phase Mapping' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'About' })).toBeVisible();
  });

  test('phase mapping tab shows editable mapping', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('tab', { name: 'Phase Mapping' }).click();
    await expect(page.getByText('Phase to Column Mapping')).toBeVisible();
    // Should have Save and Reset buttons
    await expect(page.getByRole('button', { name: 'Save' })).toBeVisible();
    await expect(page.getByText('Reset to defaults')).toBeVisible();
  });

  test('about tab shows version and plugin dirs hint', async ({ page }) => {
    await page.goto('/settings');
    await page.getByRole('tab', { name: 'About' }).click();
    await expect(page.getByText('Shipwright Command Center v0.1.0')).toBeVisible();
    await expect(page.getByText('Plugin Directories', { exact: true })).toBeVisible();
  });
});
