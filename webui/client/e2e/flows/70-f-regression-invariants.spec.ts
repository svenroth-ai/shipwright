/*
 * Flow F — Load-bearing regression guards.
 *
 * From CLAUDE.md DO-NOT rules + iterate 2/3 invariants:
 *   - No <textarea> inside /tasks/:id (DO-NOT #3 — no composer).
 *   - No chat-composer / message-input surfaces anywhere on /tasks/:id.
 *   - Terminal-launch button still fires its launch mutation.
 */

import { test, expect } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";
const UAT_PATH = "C:\\tmp\\uat-1";

async function createTask(
  request: import("@playwright/test").APIRequestContext,
  title: string,
) {
  const resp = await request.post("http://localhost:3847/api/external/tasks", {
    data: { title, cwd: UAT_PATH, projectId: UAT_PROJECT_ID },
  });
  expect(resp.ok()).toBeTruthy();
  const body = (await resp.json()) as { task: { taskId: string } };
  return body.task.taskId;
}

test.describe("Flow F — iterate-2 / iterate-3 regression guards", () => {
  test("/tasks/:id has no textarea and no composer/message-input surface", async ({
    page,
    request,
  }) => {
    const taskId = await createTask(request, `spec70f-invariants-${Date.now()}`);
    await page.goto(`/tasks/${taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();

    // DO-NOT #3: no textarea anywhere on /tasks/:id.
    await expect(page.locator("textarea")).toHaveCount(0);

    // Defensive: nothing with a test id suggesting a composer lives here.
    const composerCandidates = [
      "chat-composer",
      "message-input",
      "message-composer",
      "send-message",
      "composer",
    ];
    for (const tid of composerCandidates) {
      await expect.soft(page.locator(`[data-testid="${tid}"]`)).toHaveCount(0);
    }
    // And there is no <input type="text" placeholder~"message"> sneaking in.
    await expect.soft(page.locator('input[placeholder*="message" i]')).toHaveCount(0);

    await request.delete(`http://localhost:3847/api/external/tasks/${taskId}`);
  });

  test("Launch button on a draft task fires POST /launch and transitions state", async ({
    page,
    context,
    request,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"], {
      origin: "http://localhost:5173",
    });

    const taskId = await createTask(request, `spec70f-launch-${Date.now()}`);
    await page.goto(`/tasks/${taskId}`);
    await expect(page.getByTestId("cta-launch-in-terminal")).toBeVisible();

    const launchReq = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/api/external/tasks/${taskId}/launch`) &&
        r.request().method() === "POST",
    );
    await page.getByTestId("cta-launch-in-terminal").click();
    const resp = await launchReq;
    expect(resp.ok(), `launch must succeed — got ${resp.status()}`).toBeTruthy();

    // Task state flipped.
    const after = await request.get(`http://localhost:3847/api/external/tasks`);
    const { tasks } = (await after.json()) as { tasks: Array<{ taskId: string; state: string }> };
    const server = tasks.find((t) => t.taskId === taskId);
    expect(server?.state).not.toBe("draft");

    await request.delete(`http://localhost:3847/api/external/tasks/${taskId}`);
  });
});
