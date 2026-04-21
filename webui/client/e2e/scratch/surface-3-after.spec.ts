/**
 * Iterate-3 remediation v2 — Surface S3 AFTER verify.
 *
 * Asserts the two Surface S3 bug fixes:
 *
 *   Bug 1: Copy button in CommandPreviewPanel is gone.
 *          → `command-preview-copy` absent (all three modes).
 *          → `command-preview-panel` still renders.
 *          → `new-issue-launch-btn` still present and clickable without
 *            throwing (we don't actually assert clipboard-read because
 *            Playwright's clipboard-read permission is flaky on Windows
 *            file:// baselines; instead we verify the Launch button is
 *            the surviving copy affordance).
 *
 *   Bug 2: Modal no longer shifts when toggling Guided↔Autonomous.
 *          → pipeline + iterate modes: modal bounding-box height stays
 *            within ±2 px across the toggle.
 *          → Also asserts the `autonomy-hint` slot itself is stable
 *            (the fix is a min-height reservation on that slot).
 *
 * Captures full-page screenshots in both modes for traceability:
 *   e2e/screenshots/surface-3-guided-after.png
 *   e2e/screenshots/surface-3-autonomous-after.png
 */
import { test, expect } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";
const HEIGHT_TOLERANCE_PX = 2;

test.describe("Surface S3 after — Wizard modal polish", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("webui.activeProjectId", id);
      } catch {
        /* noop */
      }
    }, UAT_PROJECT_ID);
  });

  test("pipeline modal: Guided↔Autonomous stable height + no Copy + Launch present", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    await page.getByTestId("create-menu-caret").click();
    await page.getByTestId("create-menu-item-new-pipeline").click();

    const modal = page.getByTestId("new-issue-modal-new-pipeline");
    await expect(modal).toBeVisible();
    await page.waitForTimeout(400);

    // Bug 1: Copy button absent inside the panel.
    await expect(page.getByTestId("command-preview-panel")).toBeVisible();
    await expect(page.getByTestId("command-preview-copy")).toHaveCount(0);

    // Bug 2a: measure Guided state, full-page screenshot.
    const guidedBox = await modal.boundingBox();
    const guidedHintBox = await page.getByTestId("autonomy-hint").boundingBox();
    await page.screenshot({
      path: "e2e/screenshots/surface-3-guided-after.png",
      fullPage: true,
    });

    // Bug 2b: switch to Autonomous and re-measure.
    await page.getByTestId("autonomy-autonomous").click();
    await page.waitForTimeout(400);
    const autonomousBox = await modal.boundingBox();
    const autonomousHintBox = await page.getByTestId("autonomy-hint").boundingBox();
    await page.screenshot({
      path: "e2e/screenshots/surface-3-autonomous-after.png",
      fullPage: true,
    });

    const guidedH = guidedBox?.height ?? 0;
    const autonomousH = autonomousBox?.height ?? 0;
    const modalDelta = Math.abs(guidedH - autonomousH);
    const guidedHintH = guidedHintBox?.height ?? 0;
    const autonomousHintH = autonomousHintBox?.height ?? 0;
    const hintDelta = Math.abs(guidedHintH - autonomousHintH);

    // eslint-disable-next-line no-console
    console.log(
      `[surface-3-after] pipeline: modal guided=${guidedH}, autonomous=${autonomousH}, delta=${modalDelta} | hint guided=${guidedHintH}, autonomous=${autonomousHintH}, delta=${hintDelta}`,
    );

    // Primary assertion: modal outer height stays within ±2 px.
    expect(modalDelta).toBeLessThanOrEqual(HEIGHT_TOLERANCE_PX);
    // Secondary assertion: the hint slot is now stable (was 16.5px before).
    expect(hintDelta).toBeLessThanOrEqual(HEIGHT_TOLERANCE_PX);

    // Bug 1 tail-end: Launch button present + click does not throw (the
    // button is disabled until a title is entered; once enabled, the click
    // path handles clipboard writes internally).
    const launchBtn = page.getByTestId("new-issue-launch-btn");
    await expect(launchBtn).toBeVisible();
    await expect(launchBtn).toBeDisabled();
    await page.getByTestId("new-issue-title-input").fill("Surface 3 smoke");
    await page.waitForTimeout(100);
    await expect(launchBtn).toBeEnabled();
    // Do not actually click Launch — it POSTs to the server and navigates.
    // Presence + enabled state is what Bug 1's invariant requires.

    // Close cleanly.
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);

    expect(consoleErrors).toEqual([]);
  });

  test("iterate modal: Guided↔Autonomous stable height", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    await page.getByTestId("create-menu-caret").click();
    await page.getByTestId("create-menu-item-new-iterate").click();

    const modal = page.getByTestId("new-issue-modal-new-iterate");
    await expect(modal).toBeVisible();
    await page.waitForTimeout(400);

    await expect(page.getByTestId("command-preview-copy")).toHaveCount(0);

    const guidedBox = await modal.boundingBox();
    await page.getByTestId("autonomy-autonomous").click();
    await page.waitForTimeout(400);
    const autonomousBox = await modal.boundingBox();

    const guidedH = guidedBox?.height ?? 0;
    const autonomousH = autonomousBox?.height ?? 0;
    const delta = Math.abs(guidedH - autonomousH);
    // eslint-disable-next-line no-console
    console.log(
      `[surface-3-after] iterate: modal guided=${guidedH}, autonomous=${autonomousH}, delta=${delta}`,
    );
    expect(delta).toBeLessThanOrEqual(HEIGHT_TOLERANCE_PX);

    await page.keyboard.press("Escape");
    expect(consoleErrors).toEqual([]);
  });

  test("task modal: no Copy button in panel (Task mode has no AutonomyToggle)", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Primary button of the split = first action, which is new-task.
    await page.getByTestId("create-menu-primary").click();

    const modal = page.getByTestId("new-issue-modal-new-task");
    await expect(modal).toBeVisible();
    await expect(page.getByTestId("command-preview-panel")).toBeVisible();
    await expect(page.getByTestId("command-preview-copy")).toHaveCount(0);
    // Task mode does not render AutonomyToggle — FR-03.72 regression guard.
    await expect(page.getByTestId("autonomy-toggle")).toHaveCount(0);

    await page.keyboard.press("Escape");
    expect(consoleErrors).toEqual([]);
  });
});
