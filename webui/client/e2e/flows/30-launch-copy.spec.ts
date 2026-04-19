/*
 * Spec 30 — Kanban → Task Detail → Launch (Copy) → 3 copy rows visible +
 * state transitions to `awaiting_external_start`. Plan D'' Sub-iterate 2
 * primary end-to-end acceptance test.
 */

import { test, expect } from "@playwright/test";

test.describe("Launch (Copy)", () => {
  test("creates task → launch surfaces 3 copy rows + transitions state", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    const title = `e2e-launch-${Date.now()}`;
    await page.getByTestId("task-title-input").fill(title);
    await page.getByTestId("task-cwd-input").fill("C:/tmp/e2e-launch");
    await page.getByTestId("task-create-btn").click();

    // Auto-navigates to /tasks/:taskId.
    await expect(page.getByTestId("task-detail-page")).toBeVisible();
    await expect(page.getByTestId("task-state-badge")).toHaveText("draft");

    await page.getByTestId("launch-copy-btn").click();

    await expect(page.getByTestId("copy-command-card")).toBeVisible();
    await expect(page.getByTestId("copy-ps")).toBeVisible();
    await expect(page.getByTestId("copy-cmd")).toBeVisible();
    await expect(page.getByTestId("copy-posix")).toBeVisible();

    await expect(page.getByTestId("task-state-badge")).toHaveText("awaiting_external_start");

    const ps = await page.getByTestId("copy-ps").textContent();
    expect(ps).toMatch(/--session-id '[0-9a-f-]{36}'/);
    expect(ps).toContain("C:/tmp/e2e-launch");
  });
});
