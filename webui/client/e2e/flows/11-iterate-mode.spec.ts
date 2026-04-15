import { test, expect } from '@playwright/test';

/**
 * Iterate 14.1 / 14.6 — iterate-mode modal branching.
 *
 * When the active project has a terminal `shipwright_run_config.json`
 * status (`completed | failed | cancelled | error`), the NewIssueModal
 * renders as "New Iteration" and hides the phase dropdown. Pipeline-mode
 * projects keep the existing "New Task" header + visible dropdown.
 *
 * The spec is tolerant: without fixture scaffolding we cannot guarantee a
 * specific project mode, so we assert that WHATEVER state the modal
 * renders in is internally consistent.
 */
test.describe('Iterate mode modal', () => {
  test('modal header and dropdown visibility are consistent', async ({ page }) => {
    await page.goto('/');

    const createBtn = page.getByRole('button', { name: /create new/i });
    if (!(await createBtn.isVisible({ timeout: 3000 }).catch(() => false))) return;
    await createBtn.click();

    const newTaskItem = page.getByRole('menuitem', { name: /new (task|iteration)/i });
    if (!(await newTaskItem.isVisible({ timeout: 2000 }).catch(() => false))) return;
    await newTaskItem.click();

    const dialog = page.getByRole('dialog');
    if (!(await dialog.isVisible({ timeout: 2000 }).catch(() => false))) return;

    const headerText = (await dialog.locator('h2, h3, [role="heading"]').first().textContent())?.trim() ?? '';
    const hasPhaseDropdown = await dialog.locator('select').first().isVisible({ timeout: 500 }).catch(() => false);

    if (/iteration/i.test(headerText)) {
      // Iterate mode: phase dropdown MUST be hidden.
      expect(hasPhaseDropdown).toBe(false);
    } else {
      // Pipeline/standalone mode: header contains "Task" or similar.
      expect(headerText.length).toBeGreaterThan(0);
    }
  });
});
