/*
 * Spec 41 — Delete an active task while the CLI is still writing.
 *
 * Webui stops tracking the task; the user's terminal session keeps writing
 * to the JSONL on disk (we don't touch it). The board no longer shows the
 * card; navigation to the (now-deleted) detail page returns the not-found
 * fallback / redirects.
 *
 * Confirm-delete dialog appears for non-terminal states; clicking confirm
 * actually removes the task.
 */

import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Delete active task", () => {
  test("confirm dialog → delete → board no longer shows the card", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "delete-active-spec", cwd: "C:/tmp/delete-active" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    // Drive task to `active` by seeding JSONL.
    const encodedDir = path.join(PROJECTS_DIR, `e2e-delete-active-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    writeFileSync(
      path.join(encodedDir, `${task.sessionUuid}.jsonl`),
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: "warming up" },
      }) + "\n",
      "utf-8",
    );

    // Detail page polling kicks the state machine into "active". The
    // TaskBoard endpoint does NOT trigger transitions on its own.
    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-state-badge")).toHaveText("active", { timeout: 8000 });

    await page.goto("/");
    const card = page.getByTestId(`task-card-${task.taskId}`);
    await expect(card).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId(`task-card-state-${task.taskId}`)).toHaveText("active", {
      timeout: 8000,
    });

    await page.getByTestId(`task-card-menu-${task.taskId}`).click();
    await page.getByTestId(`task-card-delete-${task.taskId}`).click();

    const dialog = page.getByTestId("confirm-delete-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("delete-active-spec");
    await page.getByTestId("confirm-delete-confirm").click();

    await expect(page.getByTestId(`task-card-${task.taskId}`)).toHaveCount(0, { timeout: 5000 });

    // Backend confirms deletion.
    const verify = await request.get(`/api/external/tasks/${task.taskId}`);
    expect(verify.status()).toBe(404);
  });

  test("draft state deletes immediately without confirm dialog", async ({ page, request }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "draft-delete-spec", cwd: "C:/tmp/draft-delete" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto("/");
    const card = page.getByTestId(`task-card-${task.taskId}`);
    await expect(card).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId(`task-card-state-${task.taskId}`)).toHaveText("draft");

    await page.getByTestId(`task-card-menu-${task.taskId}`).click();
    await page.getByTestId(`task-card-delete-${task.taskId}`).click();

    // No dialog for draft; card vanishes directly.
    await expect(page.getByTestId("confirm-delete-dialog")).toHaveCount(0);
    await expect(page.getByTestId(`task-card-${task.taskId}`)).toHaveCount(0, { timeout: 5000 });
  });
});
