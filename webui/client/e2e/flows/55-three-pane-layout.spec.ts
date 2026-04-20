/*
 * Spec 55 — TaskDetail 3-pane layout smoke.
 *
 * Minimal happy-path coverage per section 04b:
 *   - Header, folder tree, transcript, smart viewer all render.
 *   - Two splitters are in the DOM with role="separator".
 *   - localStorage round-trip: arrow-key on a splitter persists width.
 *
 * Unit tests (`TaskDetailThreePane.test.tsx`, `useThreePaneLayout.test.ts`)
 * already cover the keyboard / clamp / invalid-JSON edge cases; this
 * spec proves the surface renders inside the real router + real server
 * round-trip.
 */

import { test, expect } from "@playwright/test";

test.describe("TaskDetail 3-pane layout", () => {
  test("header + folder tree + transcript + smart viewer render; splitters are separators", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "three-pane-smoke", cwd: "C:/tmp/three-pane" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();
    await expect(page.getByTestId("task-detail-header")).toBeVisible();
    await expect(page.getByTestId("folder-tree")).toBeVisible();
    await expect(page.getByTestId("task-detail-transcript")).toBeVisible();
    await expect(page.getByTestId("task-detail-viewer")).toBeVisible();

    const splitters = page.locator('[data-testid^="splitter-"][role="separator"]');
    await expect(splitters).toHaveCount(2);
  });

  test("keyboard ArrowRight on left splitter persists leftWidth in localStorage", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "three-pane-persist", cwd: "C:/tmp/three-pane-persist" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("splitter-left")).toBeVisible();
    const splitter = page.getByTestId("splitter-left");
    await splitter.focus();
    await page.keyboard.press("ArrowRight");
    // Debounce is 200 ms on width writes — give it a beat to land.
    await page.waitForFunction(() => {
      const raw = localStorage.getItem("webui.taskDetail.leftWidth");
      return raw !== null && Number(JSON.parse(raw)) > 240;
    }, { timeout: 2000 });
  });
});
