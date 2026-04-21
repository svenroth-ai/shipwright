/**
 * Iterate-3 remediation v2 — Surface S3 BEFORE capture.
 *
 * Opens the New Task modal (new-pipeline action, because Task mode does NOT
 * render AutonomyToggle per FR-03.72 — the Guided↔Autonomous jitter bug
 * only exists in pipeline + iterate modes). Captures:
 *   - `surface-3-guided-before.png` — modal at first paint (Guided default).
 *   - `surface-3-autonomous-before.png` — modal after clicking Autonomous.
 *
 * Also measures the modal bounding-box height in each mode and logs the
 * delta to the test report — this is the baseline for the after-spec's
 * ±2 px assertion.
 */
import { test, expect } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";

test.describe("Surface S3 before — Guided↔Autonomous jitter baseline", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("webui.activeProjectId", id);
      } catch {
        /* noop */
      }
    }, UAT_PROJECT_ID);
  });

  test("pipeline modal height in Guided + Autonomous + screenshots", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Open the caret dropdown, then New pipeline (has AutonomyToggle).
    await page.getByTestId("create-menu-caret").click();
    await page.getByTestId("create-menu-item-new-pipeline").click();

    const modal = page.getByTestId("new-issue-modal-new-pipeline");
    await expect(modal).toBeVisible();
    await page.waitForTimeout(400);

    const guidedBox = await modal.boundingBox();
    const guidedHintBox = await page.getByTestId("autonomy-hint").boundingBox();
    await page.screenshot({
      path: "e2e/screenshots/surface-3-guided-before.png",
      fullPage: true,
    });

    await page.getByTestId("autonomy-autonomous").click();
    await page.waitForTimeout(400);

    const autonomousBox = await modal.boundingBox();
    const autonomousHintBox = await page.getByTestId("autonomy-hint").boundingBox();
    await page.screenshot({
      path: "e2e/screenshots/surface-3-autonomous-before.png",
      fullPage: true,
    });

    const guidedH = guidedBox?.height ?? 0;
    const autonomousH = autonomousBox?.height ?? 0;
    const guidedHintH = guidedHintBox?.height ?? 0;
    const autonomousHintH = autonomousHintBox?.height ?? 0;
    // eslint-disable-next-line no-console
    console.log(
      `[surface-3-before] pipeline: modal guided=${guidedH}, autonomous=${autonomousH}, delta=${Math.abs(guidedH - autonomousH)} | hint guided=${guidedHintH}, autonomous=${autonomousHintH}, delta=${Math.abs(guidedHintH - autonomousHintH)}`,
    );

    await expect(page.getByTestId("command-preview-copy")).toBeVisible();
  });

  test("iterate modal height in Guided + Autonomous (narrower, wraps differently)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    await page.getByTestId("create-menu-caret").click();
    await page.getByTestId("create-menu-item-new-iterate").click();

    const modal = page.getByTestId("new-issue-modal-new-iterate");
    await expect(modal).toBeVisible();
    await page.waitForTimeout(400);

    const guidedBox = await modal.boundingBox();
    const guidedHintBox = await page.getByTestId("autonomy-hint").boundingBox();

    await page.getByTestId("autonomy-autonomous").click();
    await page.waitForTimeout(400);

    const autonomousBox = await modal.boundingBox();
    const autonomousHintBox = await page.getByTestId("autonomy-hint").boundingBox();

    const guidedH = guidedBox?.height ?? 0;
    const autonomousH = autonomousBox?.height ?? 0;
    const guidedHintH = guidedHintBox?.height ?? 0;
    const autonomousHintH = autonomousHintBox?.height ?? 0;
    // eslint-disable-next-line no-console
    console.log(
      `[surface-3-before] iterate: modal guided=${guidedH}, autonomous=${autonomousH}, delta=${Math.abs(guidedH - autonomousH)} | hint guided=${guidedHintH}, autonomous=${autonomousHintH}, delta=${Math.abs(guidedHintH - autonomousHintH)}`,
    );
  });
});
