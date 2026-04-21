/**
 * Iterate 3 remediation v2 — Surface 1 (TaskBoard) AFTER journey.
 *
 * Walks the user through the polished TaskBoard:
 *   1. Board view visible, columns present.
 *   2. Capture an "after" full-page screenshot (board view).
 *   3. Hover a task card — confirm launch/resume pill has a text label.
 *   4. Toggle to List view, capture screenshot.
 *   5. Toggle back to Board view.
 *   6. Open the "+ New ▾" dropdown, capture screenshot (confirms tightened
 *      width without description subtitles).
 *   7. Open the project filter dropdown, switch to "All Projects", confirm
 *      the header trigger label updates without a rerender race.
 *   8. Click the body of a task card (not the title) — confirm it navigates
 *      to TaskDetail.
 *   9. Assert NO console errors across the whole journey.
 *
 * Scratch spec — not run by the 70-* regression suite.
 */
import { test, expect } from "@playwright/test";

test.describe("surface-1 AFTER journey", () => {
  test("TaskBoard full polish walkthrough", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // 1. Board view.
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await expect(page.getByTestId("view-toggle-root")).toBeVisible();
    await expect(page.getByTestId("view-toggle-board")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // Settle before screenshot.
    await page.waitForTimeout(2500);

    // 2. After full-page.
    await page.screenshot({
      path: "e2e/screenshots/surface-1-after.png",
      fullPage: true,
    });

    // 3. Hover first card + capture a state showing the compact labeled pill.
    //    Find ANY existing task card (id prefix task-card-).
    const cards = page.locator('[data-testid^="task-card-"]:not([data-testid*="open-"]):not([data-testid*="menu-"]):not([data-testid*="state-"]):not([data-testid*="time-"]):not([data-testid*="commit-"]):not([data-testid*="close-"]):not([data-testid*="delete-"]):not([data-testid*="start-"])');
    const anyCard = cards.first();
    if ((await cards.count()) > 0) {
      await anyCard.scrollIntoViewIfNeeded();
      await anyCard.hover();
      await page.waitForTimeout(350);
      await page.screenshot({
        path: "e2e/screenshots/surface-1-after-hover.png",
        fullPage: false,
      });
    }

    // 4. Toggle to List view.
    await page.getByTestId("view-toggle-list").click();
    await expect(page.getByTestId("view-toggle-list")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("task-list-view")).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: "e2e/screenshots/surface-1-after-list.png",
      fullPage: true,
    });

    // 5. Back to board.
    await page.getByTestId("view-toggle-board").click();
    await expect(page.getByTestId("view-toggle-board")).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // 6. Open "+ New" dropdown.
    await page.getByTestId("create-menu-caret").click();
    // Let the Radix portal paint.
    await page.waitForTimeout(300);
    await page.screenshot({
      path: "e2e/screenshots/surface-1-after-new-menu.png",
      fullPage: false,
    });
    // Close it.
    await page.keyboard.press("Escape");

    // 7. Project filter switch. Open dropdown and click "All Projects".
    await page.getByTestId("project-filter-dropdown").click();
    await page.waitForTimeout(300);
    const allProjectsRow = page.getByTestId("project-filter-dropdown-item-all");
    await expect(allProjectsRow).toBeVisible();
    await allProjectsRow.click();
    await page.waitForTimeout(500);
    // Trigger should now read "All projects".
    await expect(page.getByTestId("project-filter-dropdown")).toContainText(
      "All projects",
    );
    await page.screenshot({
      path: "e2e/screenshots/surface-1-after-all-projects.png",
      fullPage: true,
    });

    // 8. Card body click — pick the first card and click on its body area.
    //    We already located `anyCard` above.
    if ((await cards.count()) > 0) {
      const firstCard = cards.first();
      await firstCard.scrollIntoViewIfNeeded();
      // Click near the center of the card — NOT on the title or menu.
      await firstCard.click({ position: { x: 100, y: 60 } });
      // The router navigates to /tasks/:taskId.
      await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
    }

    // 9. Assert no console errors across the whole journey.
    // eslint-disable-next-line no-console
    console.log("AFTER console errors:", JSON.stringify(consoleErrors));
    expect(consoleErrors).toEqual([]);
  });
});
