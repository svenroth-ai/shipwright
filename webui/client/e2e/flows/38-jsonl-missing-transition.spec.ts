/*
 * Spec 38 — `jsonl_missing` state transition.
 *
 * Seed a JSONL, observe state = active, delete the JSONL on disk, observe
 * state flip to `jsonl_missing` within ~2 polling cycles. Validates the
 * state-machine logic in `external/routes.ts` transcript handler.
 */

import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("State transition — jsonl_missing", () => {
  test("flips from active to jsonl_missing when the JSONL is removed mid-flight", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "missing-spec", cwd: "C:/tmp/missing-spec" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-missing-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);
    writeFileSync(
      jsonlPath,
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: "before delete" },
      }) + "\n",
      "utf-8",
    );

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-state-badge")).toHaveText("active", { timeout: 5000 });

    rmSync(jsonlPath);
    expect(existsSync(jsonlPath)).toBe(false);

    // Polling cadence ~ 1 s; allow up to 4 cycles for the state machine to flip.
    await expect(page.getByTestId("task-state-badge")).toHaveText("jsonl_missing", {
      timeout: 6000,
    });
  });
});
