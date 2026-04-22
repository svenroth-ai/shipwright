/*
 * Spec 61 — Inbox project filter (iterate 3 section 05).
 *
 * Mirrors the shape of spec 49 (TaskBoard project filter). Seeds two
 * projects with one task each, each task carrying a pending
 * AskUserQuestion tool_use in its own JSONL. Exercises the Inbox's
 * consumption of the shared `useProjectFilter` hook (FR-03.41):
 *
 *   1. All Projects → both inbox items visible.
 *   2. Switch to project B via URL (?projectId=<id>) → only B's item.
 *   3. Switch to project A → only A's item.
 *
 * Uses the URL knob rather than clicking a chip so this spec stays
 * decoupled from exactly where the chip bar is rendered in the page
 * header. Section-05's chip UI is covered in UAT; here we validate the
 * filter contract.
 */

import { test, expect } from "@playwright/test";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Inbox project filter (iterate 3 section 05)", () => {
  test("active-project toggles filter the inbox groups", async ({ page, request }) => {
    const suffix = Date.now();

    // Two real projects. Seeding against process.cwd() bypasses the
    // existsSync guard in ProjectManager.create (same trick as spec 49).
    const projA = await request.post("/api/projects", {
      data: {
        name: `inbox-proj-a-${suffix}`,
        path: process.cwd(),
        profile: "default",
        status: "active",
      },
    });
    const projB = await request.post("/api/projects", {
      data: {
        name: `inbox-proj-b-${suffix}`,
        path: process.cwd(),
        profile: "default",
        status: "active",
      },
    });
    const { data: aBody } = (await projA.json()) as { data: { id: string } };
    const { data: bBody } = (await projB.json()) as { data: { id: string } };

    // One task per project.
    const tA = await request.post("/api/external/tasks", {
      data: {
        title: `inbox-task-A-${suffix}`,
        cwd: `C:/tmp/inbox-flt-A-${suffix}`,
        projectId: aBody.id,
      },
    });
    const tB = await request.post("/api/external/tasks", {
      data: {
        title: `inbox-task-B-${suffix}`,
        cwd: `C:/tmp/inbox-flt-B-${suffix}`,
        projectId: bBody.id,
      },
    });
    const { task: taskA } = (await tA.json()) as {
      task: { taskId: string; sessionUuid: string };
    };
    const { task: taskB } = (await tB.json()) as {
      task: { taskId: string; sessionUuid: string };
    };

    // Seed one pending AskUserQuestion per task.
    const toolIdA = `e2e-tu-A-${suffix}`;
    const toolIdB = `e2e-tu-B-${suffix}`;

    const dirA = path.join(PROJECTS_DIR, `e2e-inbox-flt-A-${suffix}`);
    const dirB = path.join(PROJECTS_DIR, `e2e-inbox-flt-B-${suffix}`);
    mkdirSync(dirA, { recursive: true });
    mkdirSync(dirB, { recursive: true });
    const jsonlA = path.join(dirA, `${taskA.sessionUuid}.jsonl`);
    const jsonlB = path.join(dirB, `${taskB.sessionUuid}.jsonl`);

    const seedFor = (sessionUuid: string, toolId: string) =>
      JSON.stringify({
        type: "assistant",
        sessionId: sessionUuid,
        message: {
          content: [
            {
              type: "tool_use",
              id: toolId,
              name: "AskUserQuestion",
              input: { parts: [{ question: `proceed in ${toolId}?` }] },
            },
          ],
        },
      }) + "\n";

    writeFileSync(jsonlA, seedFor(taskA.sessionUuid, toolIdA), "utf-8");
    writeFileSync(jsonlB, seedFor(taskB.sessionUuid, toolIdB), "utf-8");

    // ── 1. All Projects — both items visible. ────────────────────────
    await page.goto("/inbox");
    await expect(page.getByTestId("inbox-page")).toBeVisible();
    // Inbox derivation walks every persisted task — allow generous time.
    await expect(page.getByTestId(`inbox-item-${toolIdA}`)).toBeVisible({
      timeout: 25_000,
    });
    await expect(page.getByTestId(`inbox-item-${toolIdB}`)).toBeVisible({
      timeout: 25_000,
    });

    // ── 2. Filter to project B — only B's item. ──────────────────────
    await page.goto(`/inbox?projectId=${bBody.id}`);
    await expect(page.getByTestId("inbox-page")).toBeVisible();
    await expect(page.getByTestId(`inbox-item-${toolIdB}`)).toBeVisible({
      timeout: 25_000,
    });
    await expect(page.getByTestId(`inbox-item-${toolIdA}`)).toBeHidden();

    // ── 3. Filter to project A — only A's item. ──────────────────────
    await page.goto(`/inbox?projectId=${aBody.id}`);
    await expect(page.getByTestId("inbox-page")).toBeVisible();
    await expect(page.getByTestId(`inbox-item-${toolIdA}`)).toBeVisible({
      timeout: 25_000,
    });
    await expect(page.getByTestId(`inbox-item-${toolIdB}`)).toBeHidden();

    // ── Cleanup. Append matching tool_results so the inbox is empty
    //    when the next test run starts; delete tasks + projects.
    appendFileSync(
      jsonlA,
      JSON.stringify({
        type: "user",
        sessionId: taskA.sessionUuid,
        message: {
          content: [{ type: "tool_result", tool_use_id: toolIdA, content: "ok" }],
        },
      }) + "\n",
      "utf-8",
    );
    appendFileSync(
      jsonlB,
      JSON.stringify({
        type: "user",
        sessionId: taskB.sessionUuid,
        message: {
          content: [{ type: "tool_result", tool_use_id: toolIdB, content: "ok" }],
        },
      }) + "\n",
      "utf-8",
    );
    await request.delete(`/api/external/tasks/${taskA.taskId}`);
    await request.delete(`/api/external/tasks/${taskB.taskId}`);
    await request.delete(`/api/projects/${aBody.id}`);
    await request.delete(`/api/projects/${bBody.id}`);
  });
});
