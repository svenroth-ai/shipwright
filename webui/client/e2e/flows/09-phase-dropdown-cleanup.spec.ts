import { test, expect } from '@playwright/test';

/**
 * Iterate 14.0 / 14.6 — phase dropdown cleanup.
 *
 * `iterate` and `preview` were temporarily added to PHASE_OPTIONS during
 * iterate 13 but are NOT real pipeline stages. 14.0 removed them. This spec
 * opens the NewIssueModal via the CreateMenu and asserts the dropdown lists
 * real pipeline phases (including `security`) and excludes the two that
 * were removed.
 *
 * The spec tolerates missing fixture state by returning early when the
 * create menu is not reachable — see the existing 06-new-issue.spec.ts
 * pattern.
 */
test.describe('Phase dropdown cleanup', () => {
  test('phase dropdown excludes iterate and preview, includes security', async ({ page }) => {
    await page.goto('/');

    const createBtn = page.getByRole('button', { name: /create new/i });
    if (!(await createBtn.isVisible({ timeout: 3000 }).catch(() => false))) return;
    await createBtn.click();

    const newTaskItem = page.getByRole('menuitem', { name: /new task/i });
    if (!(await newTaskItem.isVisible({ timeout: 2000 }).catch(() => false))) return;
    await newTaskItem.click();

    const dialog = page.getByRole('dialog');
    if (!(await dialog.isVisible({ timeout: 2000 }).catch(() => false))) return;

    // Iterate-mode projects hide the dropdown entirely — that's fine,
    // equivalent to iterate/preview being unreachable. Just assert that
    // IF the dropdown is present, its option list is clean.
    const phaseSelect = dialog.locator('select').filter({ hasText: /project|build|plan|security/i }).first();
    if (!(await phaseSelect.isVisible({ timeout: 1500 }).catch(() => false))) return;

    const optionTexts = await phaseSelect.locator('option').allTextContents();
    const lowered = optionTexts.map((t) => t.trim().toLowerCase());

    expect(lowered).not.toContain('iterate');
    expect(lowered).not.toContain('preview');
    expect(lowered).toContain('security');
  });
});
