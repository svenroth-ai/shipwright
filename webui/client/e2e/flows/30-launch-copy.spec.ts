/*
 * Spec 30 — Kanban → Task Detail → Launch (Copy) → 3 copy rows visible +
 * state transitions to `awaiting_external_start`. Plan D'' Sub-iterate 2
 * primary end-to-end acceptance test.
 *
 * Iterate 3 section 03: the legacy inline create-task form on TaskBoardPage
 * was replaced by the `+ New ▾` split-button + NewIssueModal. The simplest
 * reliable path for this spec is to POST /api/external/tasks (the same
 * API the modal ultimately hits) and then navigate to /tasks/:id — the
 * UI-level launch behaviour has not changed. The `+ New ▾` flow is covered
 * by the new 50-series specs.
 */

import { test, expect } from "@playwright/test";

test.describe("Launch (Copy)", () => {
  test("creates task → launch surfaces 3 copy rows + transitions state", async ({ page, request }) => {
    const title = `e2e-launch-${Date.now()}`;
    const create = await request.post("/api/external/tasks", {
      data: { title, cwd: "C:/tmp/e2e-launch" },
    });
    expect(create.status()).toBe(200);
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
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
