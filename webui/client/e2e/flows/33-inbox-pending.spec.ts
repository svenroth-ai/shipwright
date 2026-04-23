/*
 * Spec 33 — Inbox pending. Seed a JSONL with a pending AskUserQuestion
 * tool_use; assert it surfaces on /inbox as a visible inbox card. Appending
 * a matching tool_result clears it.
 *
 * Iterate 3.9b update: `inbox-item-<toolUseId>` is the legacy-compat hidden
 * span (aria-hidden); the visible card wrapper is `inbox-card-<toolUseId>`.
 * Best-effort badge was removed during iterate 3.7d — assertion dropped.
 */

import { test, expect } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Inbox pending", () => {
  test("surfaces pending AskUserQuestion + clears on matching tool_result", async ({ page, request }) => {
    // Unique id per run so the persistent sdk-sessions store doesn't collide
    // across successive Playwright invocations.
    const toolUseId = `e2e-tu-${Date.now()}`;
    const create = await request.post("/api/external/tasks", {
      data: { title: "inbox-pending", cwd: "C:/tmp/inbox-pending" },
    });
    const { task } = (await create.json()) as {
      task: { taskId: string; sessionUuid: string };
    };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-inbox-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);
    const seed =
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: {
          content: [
            {
              type: "tool_use",
              id: toolUseId,
              name: "AskUserQuestion",
              input: { parts: [{ question: "proceed?" }] },
            },
          ],
        },
      }) + "\n";
    writeFileSync(jsonlPath, seed, "utf-8");

    await page.goto("/inbox");
    await expect(page.getByTestId("inbox-page")).toBeVisible();
    // Inbox derivation iterates all persisted tasks; with a long-lived
    // sdk-sessions store the response can take several seconds. Allow
    // 15 s for the item to appear / disappear so the assertion isn't
    // timing-coupled to test fixture accumulation.
    await expect(page.getByTestId(`inbox-card-${toolUseId}`)).toBeVisible({ timeout: 25_000 });

    // Append matching tool_result → inbox clears.
    const match =
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: [{ type: "tool_result", tool_use_id: toolUseId, content: "ok" }] },
      }) + "\n";
    appendFileSync(jsonlPath, match, "utf-8");

    await expect(page.getByTestId(`inbox-card-${toolUseId}`)).toHaveCount(0, { timeout: 25_000 });
  });
});
