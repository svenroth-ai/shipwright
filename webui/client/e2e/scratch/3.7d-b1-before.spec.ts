/**
 * Iterate 3.7d-b1 — TaskBoard BEFORE screenshots.
 *
 * Captures the pre-polish state of /taskboard (board + list view + "+ New"
 * dropdown open) so we can diff visually against the 3.7d-b1-after spec.
 */
import { test } from "@playwright/test";

test.describe("3.7d-b1 BEFORE", () => {
  test("TaskBoard board + list + new-dropdown", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);

    // 1) Board view.
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b1-before-board.png",
      fullPage: true,
    });

    // 2) "+ New ▾" dropdown open.
    await page.getByTestId("create-menu-caret").click();
    await page.waitForTimeout(300);
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b1-before-new-menu.png",
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);

    // 3) List view.
    await page.getByTestId("view-toggle-list").click();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b1-before-list.png",
      fullPage: true,
    });
  });
});
