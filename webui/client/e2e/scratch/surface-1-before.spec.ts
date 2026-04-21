/**
 * Iterate 3 remediation v2 — Surface 1 (TaskBoard) BEFORE screenshot.
 *
 * Captures the current state of /taskboard BEFORE Surface-1 UX fixes so
 * the diff against surface-1-after.png can be reviewed during verify.
 *
 * Scratch spec — not run by 70-* regression suite.
 */
import { test, expect } from "@playwright/test";

test.describe("surface-1 BEFORE", () => {
  test("TaskBoard initial state", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    // Give the columns + tasks polling a beat to settle so the screenshot
    // captures cards, not an empty skeleton.
    await page.waitForTimeout(2500);
    await page.screenshot({
      path: "e2e/screenshots/surface-1-before.png",
      fullPage: true,
    });

    // eslint-disable-next-line no-console
    console.log("BEFORE console errors:", JSON.stringify(consoleErrors));
  });
});
