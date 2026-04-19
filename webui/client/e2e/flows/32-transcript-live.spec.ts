/*
 * Spec 32 — Live transcript. Seed a synthetic JSONL at
 * ~/.claude/projects/<encoded>/<uuid>.jsonl for a newly created task, open
 * the detail page, and assert the transcript renders the seeded user +
 * assistant events within 3 seconds (polling cadence = 1 s; we allow
 * 2× to cover the first sequential tick).
 *
 * Append a new assistant line externally — assert the new event shows up
 * within another 3 seconds.
 */

import { test, expect } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Live transcript polling", () => {
  test("renders user + assistant from seeded JSONL; picks up append within 3 s", async ({ page, request }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "live-transcript", cwd: "C:/tmp/live-xcript" },
    });
    const { task } = (await create.json()) as {
      task: { taskId: string; sessionUuid: string };
    };

    // Seed synthetic JSONL at the expected storage path. The task has not
    // been launched, so the directory won't exist yet — create it.
    const encodedDir = path.join(PROJECTS_DIR, `e2e-live-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);
    const seed =
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: "hello from e2e" },
      }) +
      "\n" +
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: { content: [{ type: "text", text: "hi back" }] },
      }) +
      "\n";
    writeFileSync(jsonlPath, seed, "utf-8");

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();

    // Transcript should render both events within 3 s (one poll cycle
    // plus generous slack).
    await expect(page.getByTestId("event-user")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("event-assistant")).toBeVisible({ timeout: 5000 });

    // Append a new assistant line externally.
    const extra =
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: { content: [{ type: "text", text: "second response" }] },
      }) + "\n";
    appendFileSync(jsonlPath, extra, "utf-8");

    await expect(page.getByText("second response")).toBeVisible({ timeout: 5000 });
  });
});
