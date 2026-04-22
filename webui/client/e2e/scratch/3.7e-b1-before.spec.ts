/**
 * Iterate 3.7e-b1 — TaskBoard BEFORE capture.
 *
 * Baseline shot taken right after the 3.7e-a Foundation commit and before
 * the S1 Board fixes (columns 360 px / gutter 40 px, green Launch, filter
 * row, card buttons size=xs, project color strip, +New menu width).
 */
import { test, expect } from "@playwright/test";

test.describe("3.7e-b1 BEFORE", () => {
  test("Board baseline (post-foundation)", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await page.waitForTimeout(2000);

    await page.screenshot({
      path: "e2e/screenshots/3.7e-b1-before-board.png",
      fullPage: true,
    });

    // New menu open — to measure width before the change.
    await page.getByTestId("create-menu-caret").click();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-b1-before-new-menu.png",
      fullPage: false,
    });

    // eslint-disable-next-line no-console
    console.log("BEFORE console errors:", JSON.stringify(consoleErrors));
  });
});
