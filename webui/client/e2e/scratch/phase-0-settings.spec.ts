/**
 * Iterate 3 remediation v2 — Phase 0 browser verify.
 *
 * Validates the shared foundation:
 *   1. /settings renders without console errors, captures a full-page
 *      screenshot (confirms .page-container wrap + card groups rendered
 *      with warm-beige palette tokens).
 *   2. / (TaskBoard) renders and a scrollable surface (the column-cards
 *      area) captures a full-page screenshot so the themed scrollbar
 *      rule is visible in the artifact.
 *
 * Scratch spec, lives under e2e/scratch/ — not run by the 70-* regression
 * suite. Orchestrator invokes this directly for Phase 0 commit verification.
 */
import { test, expect } from "@playwright/test";

test.describe("iterate-3.7c-0 Phase 0 browser verify", () => {
  test("settings page renders with v2 card styling", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/settings", { waitUntil: "networkidle" });
    await expect(page.getByTestId("settings-page")).toBeVisible();
    await expect(page.getByTestId("settings-configure-actions")).toBeVisible();

    await page.screenshot({
      path: "e2e/screenshots/phase-0-settings-after.png",
      fullPage: true,
    });

    expect(consoleErrors).toEqual([]);
  });

  test("themed scrollbar surface screenshot (TaskBoard)", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // TaskBoard is full-bleed with scrollable column content — whichever
    // pane happens to render first, the global *::-webkit-scrollbar rule
    // should apply if content overflows. Even with no tasks, we capture
    // the layout so the rule exists in the DOM/stylesheet.
    await page.goto("/", { waitUntil: "networkidle" });
    await page.screenshot({
      path: "e2e/screenshots/phase-0-scrollbar-after.png",
      fullPage: true,
    });

    expect(consoleErrors).toEqual([]);
  });
});
