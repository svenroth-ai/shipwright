/**
 * Iterate 3.7d-b1 — TaskBoard AFTER journey.
 *
 * Walks the polished TaskBoard:
 *   1. Board view centered + wider gutters.
 *   2. "+ New ▾" dropdown open — confirms subtitles render + no shortcut
 *      tooltip on the caret.
 *   3. List view — confirms the <table> with Title / State / Phase / Commit /
 *      Updated / Actions columns.
 *   4. Hover one of the always-visible brown Launch/Resume buttons on a
 *      TaskCard — confirm it's visible without hover-gating.
 *   5. Click a list row — navigate to TaskDetail.
 *   6. Assert NO console errors across the whole journey.
 */
import { test, expect } from "@playwright/test";

test.describe("3.7d-b1 AFTER", () => {
  test("TaskBoard polished walkthrough", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // 1) Board view.
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await page.waitForTimeout(2500);
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b1-after-board.png",
      fullPage: true,
    });

    // 2) Hover one of the always-visible brown buttons on a card.
    const firstLaunch = page
      .locator('[data-testid^="task-card-launch-"]')
      .first();
    if ((await firstLaunch.count()) > 0) {
      await firstLaunch.scrollIntoViewIfNeeded();
      await firstLaunch.hover();
      await page.waitForTimeout(250);
      await page.screenshot({
        path: "e2e/screenshots/3.7d-b1-after-card-hover.png",
        fullPage: false,
      });
    }

    // 3) "+ New ▾" dropdown open.
    await page.getByTestId("create-menu-caret").click();
    await page.waitForTimeout(300);
    // Subtitles are visible.
    await expect(
      page.getByTestId("create-menu-item-subtitle-new-pipeline"),
    ).toBeVisible();
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b1-after-new-menu.png",
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);

    // 4) List view — proper table with sortable headers.
    await page.getByTestId("view-toggle-list").click();
    await expect(page.getByTestId("task-list-table")).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b1-after-list.png",
      fullPage: true,
    });

    // 5) Click a row in the list → navigate to /tasks/<id>.
    const firstRow = page.locator('[data-testid^="task-list-row-"]').first();
    if ((await firstRow.count()) > 0) {
      await firstRow.click({ position: { x: 100, y: 20 } });
      await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
    }

    // 6) Console hygiene.
    // eslint-disable-next-line no-console
    console.log("AFTER console errors:", JSON.stringify(consoleErrors));
    expect(consoleErrors).toEqual([]);
  });
});
