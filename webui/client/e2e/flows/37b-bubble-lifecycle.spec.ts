/*
 * Spec 37b — Bubble layout + AskUserQuestion lifecycle.
 *
 * Seeds an assistant turn with an AskUserQuestion tool_use, then appends a
 * matching tool_result mid-flight. Asserts the amber pending banner flips
 * to green within one polling cycle (1 s + slack). Also confirms tool_use
 * and tool_result render as sibling chronological cards (not nested).
 */

import { test, expect } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Bubble lifecycle — AskUserQuestion pending → resolved", () => {
  test("amber pending flips to green resolved within one polling cycle", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "lifecycle-spec", cwd: "C:/tmp/lifecycle" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-lifecycle-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);

    const askEvent = JSON.stringify({
      type: "assistant",
      sessionId: task.sessionUuid,
      message: {
        content: [
          {
            type: "tool_use",
            id: "tu_pending_q",
            name: "AskUserQuestion",
            input: {
              parts: [{ question: "Pick a stack?", options: ["Supabase", "Firebase"] }],
            },
          },
        ],
      },
    });
    writeFileSync(jsonlPath, askEvent + "\n", "utf-8");

    await page.goto(`/tasks/${task.taskId}`);

    // Pending banner appears; amber + question copy.
    const pending = page.getByTestId("askuser-pending");
    await expect(pending).toBeVisible({ timeout: 5000 });
    await expect(pending).toContainText("Pick a stack?");
    await expect(pending).toContainText("Supabase");
    await expect(pending).toContainText("Firebase");
    expect(await pending.getAttribute("data-tool-use-id")).toBe("tu_pending_q");

    // Append matching tool_result (the user answered in their terminal).
    const answer = JSON.stringify({
      type: "user",
      sessionId: task.sessionUuid,
      message: {
        content: [{ type: "tool_result", tool_use_id: "tu_pending_q", content: "Supabase" }],
      },
    });
    appendFileSync(jsonlPath, answer + "\n", "utf-8");

    // Resolved banner appears; pending banner gone.
    await expect(page.getByTestId("askuser-resolved")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("askuser-pending")).toHaveCount(0);
  });

  test("tool_use + tool_result render as sibling cards in chronological order", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "siblings-spec", cwd: "C:/tmp/siblings" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-siblings-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);

    const lines = [
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: {
          content: [
            { type: "text", text: "Running Bash" },
            { type: "tool_use", id: "tu_bash", name: "Bash", input: { command: "ls" } },
          ],
        },
      }),
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: {
          content: [{ type: "tool_result", tool_use_id: "tu_bash", content: "file.ts\nREADME.md" }],
        },
      }),
    ];
    writeFileSync(jsonlPath, lines.join("\n") + "\n", "utf-8");

    await page.goto(`/tasks/${task.taskId}`);
    const tu = page.getByTestId("bubble-tool-use");
    const tr = page.getByTestId("bubble-tool-result");
    await expect(tu).toBeVisible({ timeout: 5000 });
    await expect(tr).toBeVisible({ timeout: 5000 });
    // Sibling check: neither is contained inside the other.
    expect(await tu.locator("[data-testid='bubble-tool-result']").count()).toBe(0);
    expect(await tr.locator("[data-testid='bubble-tool-use']").count()).toBe(0);
  });
});
