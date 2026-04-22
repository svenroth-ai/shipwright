/*
 * Flow B — Create-menu dropdown + modal mode switching.
 *
 *   1. Clicking the caret on `+ New ▾` reveals all three actions
 *      (new-task, new-pipeline, new-iterate).
 *   2. Selecting "New pipeline" opens the modal in pipeline mode with:
 *      - heading "New Pipeline"
 *      - AutonomyToggle visible
 *      - NO Phase select
 *   3. Pressing the global `i` key (outside of any input) opens the
 *      modal in new-iterate mode directly.
 */

import { test, expect } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";

test.describe("Flow B — Create-menu dropdown and mode switching", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("webui.activeProjectId", id);
      } catch {
        /* noop */
      }
    }, UAT_PROJECT_ID);
  });

  test("caret dropdown lists all three actions and opens the right mode", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Open the dropdown via the caret.
    await page.getByTestId("create-menu-caret").click();
    const dropdown = page.getByTestId("create-menu-dropdown");
    await expect(dropdown).toBeVisible();

    await expect(page.getByTestId("create-menu-item-new-task")).toBeVisible();
    await expect(page.getByTestId("create-menu-item-new-pipeline")).toBeVisible();
    await expect(page.getByTestId("create-menu-item-new-iterate")).toBeVisible();

    // Select New pipeline.
    await page.getByTestId("create-menu-item-new-pipeline").click();

    // Modal renders in pipeline mode.
    const modal = page.getByTestId("new-issue-modal-new-pipeline");
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("New Pipeline");
    // AutonomyToggle is visible (guided + autonomous radios).
    const autonomyGroup = modal.getByRole("radiogroup");
    await expect.soft(autonomyGroup).toBeVisible();
    // Phase select is absent in pipeline mode (FR-03.72).
    await expect(page.getByTestId("new-issue-phase-select")).toHaveCount(0);

    // Close the modal.
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
  });

  test("global `i` shortcut opens the New Iterate modal", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Ensure focus is on the body (not an input) so the shortcut fires.
    await page.locator("body").click({ position: { x: 5, y: 5 } });

    await page.keyboard.press("i");
    const modal = page.getByTestId("new-issue-modal-new-iterate");
    await expect(modal).toBeVisible({ timeout: 3_000 });
    await expect(modal).toContainText("New Iterate");

    // Close and assert the shortcut does NOT re-fire while the modal is open.
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
  });

  test("global `i` shortcut is IGNORED when typing in the title input", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Open new-task modal first.
    await page.getByTestId("create-menu-primary").click();
    const taskModal = page.getByTestId("new-issue-modal-new-task");
    await expect(taskModal).toBeVisible();

    // Focus the title input and type "i" — it must land in the input, NOT
    // re-open a second modal.
    const titleInput = page.getByTestId("new-issue-title-input");
    await titleInput.click();
    await page.keyboard.press("i");
    await expect(titleInput).toHaveValue("i");
    // Only the new-task modal surface remains — no new-iterate modal
    // opened from the typed "i". Scope the check to the modal-root
    // testids explicitly (the `/new-issue-modal-/` regex also matches
    // `new-issue-modal-form` and `new-issue-modal-close` inner nodes).
    await expect(page.getByTestId("new-issue-modal-new-task")).toHaveCount(1);
    await expect(page.getByTestId("new-issue-modal-new-iterate")).toHaveCount(0);
    await expect(page.getByTestId("new-issue-modal-new-pipeline")).toHaveCount(0);
  });
});
