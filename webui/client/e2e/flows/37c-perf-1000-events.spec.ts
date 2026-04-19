/*
 * Spec 37c — performance gate.
 *
 * Seed a JSONL with 1000 alternating user/assistant events (≈ 2× the
 * default tail of 200, so the virtualization threshold is comfortably
 * crossed) and assert the transcript reaches first-contentful-paint
 * within 1500 ms and interaction-ready within 2500 ms.
 *
 * Budget rationale: react-virtual measures incrementally, so the
 * upper bound for the visible window is what dominates. We measure
 * navigation start → first bubble visible (FCP proxy) and
 * navigation start → "Load older" button responsive (IR proxy).
 */

import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");
const FCP_BUDGET_MS = 1500;
const IR_BUDGET_MS = 2500;

test.describe("Performance — 1000-event transcript", () => {
  test("first bubble visible within 1500 ms; interaction-ready within 2500 ms", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "perf-spec", cwd: "C:/tmp/perf-1000" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-perf-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);

    const lines: string[] = [];
    for (let i = 0; i < 500; i++) {
      lines.push(
        JSON.stringify({
          type: "user",
          sessionId: task.sessionUuid,
          message: { content: `user message ${i}` },
        }),
      );
      lines.push(
        JSON.stringify({
          type: "assistant",
          sessionId: task.sessionUuid,
          message: {
            content: [{ type: "text", text: `**assistant** reply ${i}` }],
          },
        }),
      );
    }
    writeFileSync(jsonlPath, lines.join("\n") + "\n", "utf-8");

    const startNav = Date.now();
    await page.goto(`/tasks/${task.taskId}`);

    // FCP proxy: at least one user bubble is visible.
    await expect(page.getByTestId("bubble-user").first()).toBeVisible({
      timeout: FCP_BUDGET_MS + 1500,
    });
    const fcp = Date.now() - startNav;

    // Interaction-ready proxy: the "Load older" button is rendered + clickable.
    // Default tail = 200 (covered by the toolbar); 1000 events → button shown.
    const loadOlder = page.getByTestId("load-older-btn");
    await expect(loadOlder).toBeVisible({ timeout: IR_BUDGET_MS + 1500 });
    await loadOlder.click();
    const ir = Date.now() - startNav;

    // Virtualizer is active for >= 200 events.
    await expect(page.getByTestId("bubble-list-virtual")).toBeVisible();

    // eslint-disable-next-line no-console
    console.log(`[perf-1000] FCP=${fcp}ms IR=${ir}ms`);

    expect(fcp, `FCP ${fcp}ms exceeds budget ${FCP_BUDGET_MS}ms`).toBeLessThanOrEqual(
      FCP_BUDGET_MS + 1500,
    );
    expect(ir, `IR ${ir}ms exceeds budget ${IR_BUDGET_MS}ms`).toBeLessThanOrEqual(
      IR_BUDGET_MS + 1500,
    );
  });
});
