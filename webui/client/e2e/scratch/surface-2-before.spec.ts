/**
 * Iterate 3 remediation v2 — Surface 2 (TaskDetail) BEFORE-screenshot.
 *
 * Opens a task that has a large JSONL transcript (perf-spec, 1000 events)
 * and captures the current state of the BubbleTranscript pane so we can
 * diagnose:
 *   - empty vertical gap above the first bubble
 *   - attachment chip stacking
 *   - missing timestamps
 *   - auto-scroll position
 *   - system-toggle effect
 *
 * Lives under e2e/scratch/ so the 70-* regression suite does not pick it
 * up. Invoke explicitly: `npx playwright test e2e/scratch/surface-2-before`.
 */
import { test, expect } from "@playwright/test";

const TASK_ID_1000 = "93a23815-d152-4c2f-9f8a-c20288296592"; // perf-spec, 1000 events

test.describe("iterate-3.7c-2 surface-2 BEFORE", () => {
  test("TaskDetail transcript current state (1000 events)", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto(`/tasks/${TASK_ID_1000}`, { waitUntil: "networkidle" });
    // Wait for the transcript to mount and render bubbles (at least one).
    await page.waitForSelector('[data-testid="bubble-transcript"]', { timeout: 15000 });
    // Give virtualizer + polling a moment to settle.
    await page.waitForTimeout(2500);

    await page.screenshot({
      path: "e2e/screenshots/surface-2-before.png",
      fullPage: true,
    });

    // Pane-only screenshot (center transcript section).
    const transcript = page.getByTestId("task-detail-transcript");
    await transcript.screenshot({
      path: "e2e/screenshots/surface-2-before-transcript-pane.png",
    });

    // Log observed DOM facts so we can diff later.
    const header = await page.getByTestId("task-detail-transcript-header").textContent();
    const countLabel = await page.getByTestId("transcript-event-count").textContent();
    const bubbleCount = await page
      .locator('[data-testid^="bubble-"]')
      .count();
    const userBubbles = await page.locator('[data-testid="bubble-user"]').count();
    const assistantBubbles = await page
      .locator('[data-testid="bubble-assistant"]')
      .count();
    const systemBubbles = await page.locator('[data-testid="bubble-system"]').count();
    // eslint-disable-next-line no-console
    console.log("[surface-2-before]", {
      header,
      countLabel,
      bubbleCount,
      userBubbles,
      assistantBubbles,
      systemBubbles,
      consoleErrors,
    });

    expect(bubbleCount).toBeGreaterThan(0);
  });
});
