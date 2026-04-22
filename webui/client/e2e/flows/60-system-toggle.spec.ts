/*
 * Spec 60 — System events hidden by default + toolbar toggle persistence.
 *
 * Seeds a system-heavy JSONL fixture; asserts default-hidden, clicks the
 * toolbar toggle, asserts visible, reloads, asserts toggle state persists
 * (localStorage round-trip end-to-end under key
 * `webui.transcript.showSystem`).
 */

import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");
const STORAGE_KEY = "webui.transcript.showSystem";

test.describe("System visibility toggle (FR-03.51)", () => {
  test("system events hidden by default, toggle reveals them, state persists across reload", async ({
    page,
    request,
  }) => {
    // Reset localStorage for this test to make it deterministic — the key
    // is global across tabs / tasks / reloads by design.
    await page.goto("/");
    await page.evaluate((key) => window.localStorage.removeItem(key), STORAGE_KEY);

    const create = await request.post("/api/external/tasks", {
      data: { title: "system-toggle-spec", cwd: "C:/tmp/system-toggle" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-system-toggle-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);

    // System-heavy fixture: 3 system events mixed with a normal user message
    // so the transcript is non-empty even when system bubbles are hidden.
    const lines = [
      JSON.stringify({
        type: "system",
        sessionId: task.sessionUuid,
        subtype: "init",
        content: "cwd=/tmp session=abc",
      }),
      JSON.stringify({
        type: "system",
        sessionId: task.sessionUuid,
        subtype: "local_command",
        content: "<local-command-stdout>ok</local-command-stdout>",
      }),
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: "hi" },
      }),
      JSON.stringify({
        type: "system",
        sessionId: task.sessionUuid,
        subtype: "informational",
        content: "background note",
      }),
    ];
    writeFileSync(jsonlPath, lines.join("\n") + "\n", "utf-8");

    await page.goto(`/tasks/${task.taskId}`);

    // Default: system hidden, user bubble visible.
    await expect(page.getByTestId("bubble-user")).toBeVisible({ timeout: 5000 });
    await expect(page.getByTestId("bubble-system")).toHaveCount(0);

    // Click toggle.
    const toggle = page.getByTestId("system-toggle");
    await expect(toggle).toBeVisible();
    await toggle.click();

    // System bubbles appear; count matches fixture (3 system lines).
    await expect(page.getByTestId("bubble-system").first()).toBeVisible();
    expect(await page.getByTestId("bubble-system").count()).toBe(3);

    // localStorage key flipped to "true".
    const storedAfterClick = await page.evaluate(
      (key) => window.localStorage.getItem(key),
      STORAGE_KEY,
    );
    expect(storedAfterClick).toBe("true");

    // Reload — toggle state must persist end-to-end.
    await page.reload();
    await expect(page.getByTestId("bubble-system").first()).toBeVisible({ timeout: 5000 });
    expect(await page.getByTestId("bubble-system").count()).toBe(3);

    // Cleanup: restore default-hidden for subsequent specs.
    await page.evaluate((key) => window.localStorage.removeItem(key), STORAGE_KEY);
  });
});
