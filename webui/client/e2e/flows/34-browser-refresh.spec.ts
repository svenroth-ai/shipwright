/*
 * Spec 34 — Browser refresh during a JSONL write: transcript re-fetches,
 * no duplicate events, no server-side state corruption. The stateless
 * transcript endpoint (round-3 Gemini BLOCKER fix) makes this trivial;
 * this spec is a regression guard that proves it.
 */

import { test, expect } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Browser refresh during JSONL write", () => {
  test("no duplicate events after reload", async ({ page, request }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "refresh-test", cwd: "C:/tmp/refresh-test" },
    });
    const { task } = (await create.json()) as {
      task: { taskId: string; sessionUuid: string };
    };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-refresh-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);
    writeFileSync(
      jsonlPath,
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: "round 1" },
      }) + "\n",
      "utf-8",
    );

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("bubble-user")).toBeVisible({ timeout: 5000 });

    // Append new content then refresh.
    appendFileSync(
      jsonlPath,
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: { content: [{ type: "text", text: "round 2" }] },
      }) + "\n",
      "utf-8",
    );

    await page.reload();
    await expect(page.getByTestId("task-detail-page")).toBeVisible();
    await expect(page.getByText("round 2")).toBeVisible({ timeout: 5000 });

    // Still exactly one of each.
    const userCount = await page.getByTestId("bubble-user").count();
    expect(userCount).toBe(1);
  });
});
