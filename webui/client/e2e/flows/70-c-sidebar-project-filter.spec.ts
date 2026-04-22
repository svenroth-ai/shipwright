/*
 * Flow C — Sidebar project filter + TaskBoard chip sync.
 *
 *   1. Sidebar lists "All projects" + "UAT 1".
 *   2. Click "UAT 1" in Sidebar → URL carries ?projectId=<uuid> AND the
 *      TaskBoard chip bar reflects the selection.
 *   3. Click "All projects" → URL clears; filter resets.
 *   4. Reload after setting a filter → filter persists via localStorage
 *      (URL rebuild from localStorage mirror).
 */

import { test, expect } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";

test.describe("Flow C — Sidebar project filter ↔ TaskBoard chip sync", () => {
  test("sidebar click drives URL + chip bar", async ({ page }) => {
    // Start with no filter.
    await page.addInitScript(() => {
      try {
        localStorage.removeItem("webui.activeProjectId");
      } catch {
        /* noop */
      }
    });

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Sidebar project list is visible with "All projects" + "UAT 1".
    const sidebar = page.getByTestId("sidebar-project-list");
    await expect(sidebar).toBeVisible();
    await expect(page.getByTestId("sidebar-project-all")).toBeVisible();
    const uatRow = page.getByTestId(`sidebar-project-${UAT_PROJECT_ID}`);
    await expect(uatRow).toBeVisible();

    // Click "UAT 1" in Sidebar.
    await uatRow.click();

    // URL picks up the filter.
    await expect(page).toHaveURL(new RegExp(`projectId=${UAT_PROJECT_ID}`), { timeout: 3_000 });

    // Chip bar on TaskBoard reflects it (aria-active).
    const chip = page.getByTestId(`project-chip-${UAT_PROJECT_ID}`);
    await expect(chip).toHaveAttribute("data-active", "true");

    // The Sidebar row is also marked active.
    await expect(uatRow).toHaveAttribute("data-active", "true");

    // Click "All projects" chip → URL clears.
    await page.getByTestId("project-chip-all").click();
    await expect(page).not.toHaveURL(/projectId=/);
    // Sidebar "All projects" is now active.
    await expect(page.getByTestId("sidebar-project-all")).toHaveAttribute("data-active", "true");
  });

  test("filter persists across a reload via localStorage mirror", async ({ page }) => {
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("webui.activeProjectId", id);
      } catch {
        /* noop */
      }
    }, UAT_PROJECT_ID);

    // Goto root WITHOUT a query param — the localStorage value should hydrate.
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Chip is active for UAT project.
    const chip = page.getByTestId(`project-chip-${UAT_PROJECT_ID}`);
    await expect(chip).toHaveAttribute("data-active", "true");
  });
});
