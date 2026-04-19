/*
 * Spec 35 — Regression guard: the architecture rejects any in-webui chat
 * panel. Scanning a fresh task detail must NOT produce any
 * `[data-testid^="chat-"]` or message-input textbox. If someone
 * re-introduces an inline chat UI inadvertently, this spec fails on PR.
 */

import { test, expect } from "@playwright/test";

test.describe("No chat panel (architecture guard)", () => {
  test("task detail has no chat-* testids and no message textbox", async ({ page, request }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "no-chat-guard", cwd: "C:/tmp/no-chat" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();

    // No chat-*-prefixed testids anywhere.
    const chatNodes = page.locator('[data-testid^="chat-"]');
    await expect(chatNodes).toHaveCount(0);

    // No `<input role="textbox">` or `<textarea>` used for sending messages.
    // (Task create form is on / not /tasks/:id, so textareas here are fair signals.)
    const textareas = page.locator("textarea");
    await expect(textareas).toHaveCount(0);
  });
});
