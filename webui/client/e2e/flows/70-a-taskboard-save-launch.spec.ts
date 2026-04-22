/*
 * Flow A — TaskBoard create / Save-to-Backlog / Launch-in-Terminal.
 *
 * Ground-truth coverage for the New Issue modal lifecycle from the
 * TaskBoardPage. Specifically exercises:
 *   - The "+ New" split-button opens the modal.
 *   - Save-to-Backlog:  modal closes, NO window.alert fires, task appears
 *                       in the Backlog (Draft) column, task persists after
 *                       a full reload.
 *   - Launch:           modal closes, task transitions to a non-draft
 *                       state, clipboard receives the launch command,
 *                       browser navigates to /tasks/<taskId>.
 *
 * This spec targets the live servers (localhost:3847 backend + localhost:5173
 * vite) and cleans up the tasks it creates.
 */

import { test, expect, type Dialog } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";

async function getTasks(request: import("@playwright/test").APIRequestContext) {
  const resp = await request.get("http://localhost:3847/api/external/tasks");
  expect(resp.ok()).toBeTruthy();
  return (await resp.json()) as {
    tasks: Array<{ taskId: string; title: string; state: string; projectId: string }>;
  };
}

test.describe("Flow A — TaskBoard create → save / launch", () => {
  test.beforeEach(async ({ page }) => {
    // Make sure the activeProjectId defaults to UAT 1 so the modal has
    // actions resolved (and the Save/Launch paths don't 400 on missing
    // project). Setting it BEFORE goto prevents the localStorage-race.
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("webui.activeProjectId", id);
      } catch {
        /* noop */
      }
    }, UAT_PROJECT_ID);
  });

  test("Save to Backlog lands the task in Draft without a native alert and persists across reload", async ({
    page,
    request,
  }) => {
    const title = `spec70a-save-${Date.now()}`;

    // Capture any browser-native dialog. The bug hypothesis from the
    // audit brief is that NewIssueModal's default onToast fires
    // window.alert("Saved to Backlog"), which is an iterate-3 regression.
    const dialogs: Array<{ type: string; message: string }> = [];
    const dialogListener = (dlg: Dialog) => {
      dialogs.push({ type: dlg.type(), message: dlg.message() });
      // Dismiss so Playwright doesn't time out waiting for a human.
      void dlg.dismiss().catch(() => {});
    };
    page.on("dialog", dialogListener);

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Open the modal via the primary split-button.
    await page.getByTestId("create-menu-primary").click();
    await expect(page.getByTestId("new-issue-modal-new-task")).toBeVisible();

    // Fill the required title field.
    await page.getByTestId("new-issue-title-input").fill(title);
    await page.getByTestId("new-issue-description-input").fill("seeded by Flow A spec");

    // Save to Backlog. Wait for the POST /api/external/tasks to resolve.
    const createResp = page.waitForResponse(
      (r) => r.url().includes("/api/external/tasks") && r.request().method() === "POST",
    );
    await page.getByTestId("new-issue-save-btn").click();
    const resp = await createResp;
    expect(resp.ok()).toBeTruthy();
    const createdBody = (await resp.json()) as { task?: { taskId: string } };
    const newTaskId = createdBody.task?.taskId ?? "";
    expect(newTaskId.length).toBeGreaterThan(0);

    // Give any alert() a beat to surface before we assert on it.
    await page.waitForTimeout(400);
    page.off("dialog", dialogListener);

    // ASSERT 1: no native window.alert dialog fired. A native alert is
    // hostile UX and blocks automation; iterate 3 should use inline toasts.
    expect.soft(dialogs, "no native alert/confirm/prompt should fire on Save").toEqual([]);

    // ASSERT 2: modal closes.
    await expect(page.getByTestId("new-issue-modal-new-task")).toHaveCount(0, { timeout: 5_000 });

    // ASSERT 3: we did NOT navigate away.
    expect(page.url()).not.toContain("/tasks/");

    // ASSERT 4: the task appears in the Draft column IMMEDIATELY —
    // TaskBoardPage now invalidates the external-tasks query on
    // onTaskCreated, so we should NOT have to wait for the 2s
    // refetchInterval tick. 1.5s is comfortably below that.
    // (Phase A3 — iterate 3 remediation BUG 1.)
    await expect(page.getByTestId("column-draft")).toContainText(title, { timeout: 1_500 });

    // ASSERT 5: the task persists through a hard reload (disk write).
    await page.reload();
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await expect(page.getByTestId("column-draft")).toContainText(title, { timeout: 6_000 });

    // ASSERT 6: the task has the correct projectId + draft state on the server.
    const { tasks } = await getTasks(request);
    const server = tasks.find((t) => t.taskId === newTaskId);
    expect(server, "new task must be in server list").toBeDefined();
    expect(server?.state).toBe("draft");
    expect(server?.projectId).toBe(UAT_PROJECT_ID);

    // Cleanup.
    await request.delete(`http://localhost:3847/api/external/tasks/${newTaskId}`);
  });

  test("Launch copies the command to clipboard and navigates to /tasks/:id", async ({
    page,
    context,
    request,
  }) => {
    // Permission for clipboard-read; write is granted by default for same-origin.
    await context.grantPermissions(["clipboard-read", "clipboard-write"], {
      origin: "http://localhost:5173",
    });

    const title = `spec70a-launch-${Date.now()}`;
    const dialogs: Array<{ type: string; message: string }> = [];
    const dialogListener = (dlg: Dialog) => {
      dialogs.push({ type: dlg.type(), message: dlg.message() });
      void dlg.dismiss().catch(() => {});
    };
    page.on("dialog", dialogListener);

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    await page.getByTestId("create-menu-primary").click();
    await expect(page.getByTestId("new-issue-modal-new-task")).toBeVisible();
    await page.getByTestId("new-issue-title-input").fill(title);

    // Launch via the primary submit button. Two requests fire: POST /tasks
    // then POST /tasks/:id/launch.
    const createResp = page.waitForResponse(
      (r) => r.url().endsWith("/api/external/tasks") && r.request().method() === "POST",
    );
    const launchResp = page.waitForResponse(
      (r) => /\/api\/external\/tasks\/[\w-]+\/launch$/.test(r.url()) && r.request().method() === "POST",
    );

    await page.getByTestId("new-issue-launch-btn").click();

    const created = await createResp;
    expect(created.ok()).toBeTruthy();
    const createdBody = (await created.json()) as { task: { taskId: string } };
    const newTaskId = createdBody.task.taskId;

    const launched = await launchResp;
    expect(launched.ok(), `launch request must succeed — got ${launched.status()}`).toBeTruthy();
    const launchBody = (await launched.json()) as { commands?: { posix?: string; powershell?: string } };
    const expectedClipboardText =
      launchBody.commands?.powershell ?? launchBody.commands?.posix ?? "";
    expect(expectedClipboardText.length).toBeGreaterThan(0);

    // Navigation lands on TaskDetail.
    await page.waitForURL(new RegExp(`/tasks/${newTaskId}$`), { timeout: 5_000 });
    await expect(page.getByTestId("task-detail-page")).toBeVisible();

    page.off("dialog", dialogListener);
    // No native dialog should fire on a successful launch either.
    expect.soft(dialogs, "no native alert/confirm/prompt on Launch").toEqual([]);

    // Clipboard read — compare against the server-returned command string.
    // grantPermissions('clipboard-read') should make this work in Chromium.
    let clipboard = "";
    try {
      clipboard = await page.evaluate(async () => {
        try {
          return await navigator.clipboard.readText();
        } catch {
          return "";
        }
      });
    } catch {
      /* noop — fall back to API-only assertion below */
    }

    if (clipboard.length > 0) {
      expect(clipboard).toContain("claude");
      // It should match one of the three shell forms the server returned.
      const formsMatch =
        clipboard === launchBody.commands?.powershell ||
        clipboard === launchBody.commands?.posix;
      expect.soft(formsMatch, "clipboard should match a server-returned shell form").toBeTruthy();
    } else {
      // Browser refused clipboard-read even with permission — verify the
      // server response still has the command shape we expect.
      expect.soft(expectedClipboardText).toMatch(/claude\s+\/shipwright-/);
    }

    // The task state is no longer "draft" on the server.
    const { tasks } = await getTasks(request);
    const server = tasks.find((t) => t.taskId === newTaskId);
    expect(server, "task must exist after launch").toBeDefined();
    expect(server?.state).not.toBe("draft");

    // Cleanup.
    await request.delete(`http://localhost:3847/api/external/tasks/${newTaskId}`);
  });
});
