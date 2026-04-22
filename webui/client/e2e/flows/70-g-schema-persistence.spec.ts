/*
 * Flow G — Schema v2 persistence on PATCH (ADR-038).
 *
 *   1. The live sdk-sessions.json currently reports schemaVersion 2.
 *   2. PATCH to rename a task succeeds (no 500).
 *   3. After the rename, the on-disk file is STILL schemaVersion 2 (no
 *      accidental downgrade), the renamed task carries a projectId, and
 *      the task count is preserved.
 */

import { test, expect } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";
const UAT_PATH = "C:\\tmp\\uat-1";

function storePath(): string {
  // Match server/src/config/paths.ts default for SHIPWRIGHT_WEBUI_HOME.
  const registry = process.env.SHIPWRIGHT_WEBUI_HOME
    ?? path.join(homedir(), ".shipwright-webui");
  return path.join(registry, "sdk-sessions.json");
}

test.describe("Flow G — Schema v2 persistence (ADR-038)", () => {
  test("existing v2 store rewrites v2 after a rename PATCH", async ({ request }) => {
    const file = storePath();
    test.skip(!existsSync(file), `sdk-sessions.json not found at ${file}`);

    // Snapshot before.
    const beforeRaw = readFileSync(file, "utf-8");
    const before = JSON.parse(beforeRaw) as {
      schemaVersion: number;
      sessions: Record<string, Record<string, unknown>>;
    };
    expect(before.schemaVersion).toBe(2);
    const taskCountBefore = Object.keys(before.sessions).length;

    // Create a throw-away task to rename + delete.
    const createResp = await request.post("http://localhost:3847/api/external/tasks", {
      data: {
        title: `spec70g-schema-${Date.now()}`,
        cwd: UAT_PATH,
        projectId: UAT_PROJECT_ID,
      },
    });
    expect(createResp.ok()).toBeTruthy();
    const { task } = (await createResp.json()) as { task: { taskId: string } };

    // PATCH — rename.
    const newTitle = `spec70g-renamed-${Date.now()}`;
    const patchResp = await request.patch(
      `http://localhost:3847/api/external/tasks/${task.taskId}`,
      { data: { title: newTitle } },
    );
    expect(patchResp.ok(), `PATCH must succeed — got ${patchResp.status()}`).toBeTruthy();

    // Re-read disk.
    const afterRaw = readFileSync(file, "utf-8");
    const after = JSON.parse(afterRaw) as {
      schemaVersion: number;
      sessions: Record<string, { projectId?: string; title?: string }>;
    };
    expect(after.schemaVersion, "schemaVersion must remain 2 after PATCH").toBe(2);

    const persisted = after.sessions[task.taskId];
    expect(persisted, "renamed task must be in on-disk store").toBeDefined();
    expect(persisted?.title).toBe(newTitle);
    expect(typeof persisted?.projectId).toBe("string");
    expect(persisted?.projectId?.length ?? 0).toBeGreaterThan(0);

    // Task count increased by exactly 1.
    expect(Object.keys(after.sessions).length).toBe(taskCountBefore + 1);

    // Every existing row still carries a projectId (no schema regression
    // that would silently drop the field for other tasks).
    for (const [tid, row] of Object.entries(after.sessions)) {
      expect.soft(
        typeof (row as { projectId?: unknown }).projectId,
        `task ${tid} must still carry a projectId field`,
      ).toBe("string");
    }

    // Cleanup.
    await request.delete(`http://localhost:3847/api/external/tasks/${task.taskId}`);
  });
});
