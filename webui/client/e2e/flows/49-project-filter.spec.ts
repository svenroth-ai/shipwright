/*
 * Spec 49 — project filter chip bar persists across reload (FR-03.03..05).
 *
 * Iterate 3 section 02. Creates two projects, seeds one task per project
 * via the API, then exercises the TaskBoard chip bar:
 *   1. "All projects" shows both tasks.
 *   2. Click project-B chip → only project-B card remains.
 *   3. Reload → filter persists via localStorage + URL.
 *   4. Click "All projects" → both return.
 */

import { test, expect } from "@playwright/test";

test.describe("Project filter chip bar (iterate 3 section 02)", () => {
  test("filter persists across reload + toggles back to all", async ({ page, request }) => {
    const suffix = Date.now();

    // Seed two real projects via the API. Use directories that already
    // exist on the test machine (cwd is fine) to bypass the existsSync
    // guard in ProjectManager.create.
    const projA = await request.post("/api/projects", {
      data: {
        name: `proj-a-${suffix}`,
        path: process.cwd(),
        profile: "default",
        status: "active",
      },
    });
    const projB = await request.post("/api/projects", {
      data: {
        name: `proj-b-${suffix}`,
        path: process.cwd(),
        profile: "default",
        status: "active",
      },
    });
    const { data: aBody } = (await projA.json()) as { data: { id: string } };
    const { data: bBody } = (await projB.json()) as { data: { id: string } };

    // Seed one task per project via POST /api/external/tasks + PATCH.
    const tA = await request.post("/api/external/tasks", {
      data: { title: `task-A-${suffix}`, cwd: process.cwd(), projectId: aBody.id },
    });
    const tB = await request.post("/api/external/tasks", {
      data: { title: `task-B-${suffix}`, cwd: process.cwd(), projectId: bBody.id },
    });
    const { task: taskA } = (await tA.json()) as { task: { taskId: string } };
    const { task: taskB } = (await tB.json()) as { task: { taskId: string } };

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Chip bar renders both projects.
    await expect(page.getByTestId(`project-chip-${aBody.id}`)).toBeVisible();
    await expect(page.getByTestId(`project-chip-${bBody.id}`)).toBeVisible();

    // All-projects mode — both cards visible.
    await expect(page.getByText(`task-A-${suffix}`)).toBeVisible();
    await expect(page.getByText(`task-B-${suffix}`)).toBeVisible();

    // Click project-B chip → only B remains.
    await page.getByTestId(`project-chip-${bBody.id}`).click();
    await expect(page.getByText(`task-B-${suffix}`)).toBeVisible();
    await expect(page.getByText(`task-A-${suffix}`)).not.toBeVisible();
    // URL reflects the filter.
    expect(page.url()).toContain(`projectId=${bBody.id}`);

    // Reload — filter persists (URL carries it, localStorage mirrors it).
    await page.reload();
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await expect(page.getByText(`task-B-${suffix}`)).toBeVisible();
    await expect(page.getByText(`task-A-${suffix}`)).not.toBeVisible();

    // Click "All projects" → both return.
    await page.getByTestId("project-chip-all").click();
    await expect(page.getByText(`task-A-${suffix}`)).toBeVisible();
    await expect(page.getByText(`task-B-${suffix}`)).toBeVisible();

    // Cleanup — delete both tasks so we don't leak across test runs.
    await request.delete(`/api/external/tasks/${taskA.taskId}`);
    await request.delete(`/api/external/tasks/${taskB.taskId}`);
    await request.delete(`/api/projects/${aBody.id}`);
    await request.delete(`/api/projects/${bBody.id}`);
  });
});
