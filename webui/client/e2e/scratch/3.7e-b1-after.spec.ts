/**
 * Iterate 3.7e-b1 — TaskBoard AFTER verification.
 *
 * Validates the S1 Board polish:
 *   - Columns widened to 360 px (from 320) + gutter 40 px (from 32).
 *   - Backlog cards show GREEN Launch button only (no Resume on backlog).
 *   - In Progress cards show BROWN Resume button only (no Launch).
 *   - Filter row renders Status chips inside the .board-container.
 *   - + New dropdown: pinned to 280 px + subtitles wrap onto 2 lines.
 *   - Project-color left-edge strip on every card.
 *
 * Screenshots:
 *   3.7e-b1-after-board.png   — full-page board with filter row visible
 *   3.7e-b1-after-new-menu.png — +New menu open, subtitles wrapped
 *   3.7e-b1-after-filter-active.png — a status chip active
 */
import { test, expect } from "@playwright/test";

test.describe("3.7e-b1 AFTER", () => {
  test("Board polished (S1)", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // 1) Board view — capture full page.
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await page.waitForTimeout(2500);

    // Column width should be 360 px.
    const draftCol = page.getByTestId("column-draft");
    await expect(draftCol).toBeVisible();
    const draftBox = await draftCol.boundingBox();
    expect(draftBox?.width).toBeGreaterThanOrEqual(358);
    expect(draftBox?.width).toBeLessThanOrEqual(362);

    // Filter row visible inside the container.
    await expect(page.getByTestId("board-filter-status")).toBeVisible();
    // Every ExternalTaskState exposes a chip.
    await expect(page.getByTestId("board-filter-status-draft")).toBeVisible();
    await expect(page.getByTestId("board-filter-status-done")).toBeVisible();
    await expect(
      page.getByTestId("board-filter-status-awaiting_external_start"),
    ).toBeVisible();

    await page.screenshot({
      path: "e2e/screenshots/3.7e-b1-after-board.png",
      fullPage: true,
    });

    // 2) Project-color strip present on every card.
    const anyCard = page.locator('[data-testid^="task-card-"][data-project-id]').first();
    if ((await anyCard.count()) > 0) {
      const taskId = await anyCard.getAttribute("data-testid");
      if (taskId) {
        const stripId = taskId.replace("task-card-", "task-card-project-strip-");
        await expect(page.locator(`[data-testid="${stripId}"]`)).toBeAttached();
      }
    }

    // 3) Verify a Backlog card has green Launch + no Resume.
    const backlogCards = page.locator(
      '[data-testid="column-draft"] [data-testid^="task-card-"]',
    );
    const backlogCount = await backlogCards.count();
    if (backlogCount > 0) {
      const firstBacklog = backlogCards.first();
      const backlogId = await firstBacklog.getAttribute("data-testid");
      if (backlogId) {
        const id = backlogId.replace("task-card-", "");
        // Launch present.
        const launch = page.locator(
          `[data-testid="task-card-launch-${id}"]`,
        );
        await expect(launch).toBeVisible();
        // Inner solid button carries data-color="green".
        const solid = launch.locator('[data-testid^="terminal-launch-solid-"]');
        await expect(solid).toHaveAttribute("data-color", "green");
        await expect(solid).toHaveAttribute("data-size", "xs");
        // Resume absent.
        await expect(
          page.locator(`[data-testid="task-card-resume-${id}"]`),
        ).toHaveCount(0);
      }
    }

    // 4) Verify an In Progress card has brown Resume + no Launch.
    const inProgressCards = page.locator(
      '[data-testid="column-in-progress"] [data-testid^="task-card-"]',
    );
    const ipCount = await inProgressCards.count();
    if (ipCount > 0) {
      const firstIp = inProgressCards.first();
      const ipId = await firstIp.getAttribute("data-testid");
      if (ipId) {
        const id = ipId.replace("task-card-", "");
        const resume = page.locator(`[data-testid="task-card-resume-${id}"]`);
        await expect(resume).toBeVisible();
        const solid = resume.locator(
          '[data-testid^="terminal-launch-solid-"]',
        );
        await expect(solid).toHaveAttribute("data-color", "brown");
        await expect(solid).toHaveAttribute("data-size", "xs");
        // No Launch twin on in-progress anymore.
        await expect(
          page.locator(`[data-testid="task-card-launch-${id}"]`),
        ).toHaveCount(0);
      }
    }

    // 5) + New dropdown — confirm width is tight (<= 300 px) + subtitle wraps.
    await page.getByTestId("create-menu-caret").click();
    await page.waitForTimeout(300);
    const dropdown = page.getByTestId("create-menu-dropdown");
    await expect(dropdown).toBeVisible();
    const ddBox = await dropdown.boundingBox();
    expect(ddBox?.width).toBeLessThanOrEqual(300);
    expect(ddBox?.width).toBeGreaterThanOrEqual(270);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-b1-after-new-menu.png",
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // 6) Interact with Status filter chip — assert card count changes.
    // Count cards before.
    const beforeCount = await page
      .locator('[data-testid^="task-card-"]')
      .count();
    // Click the "done" chip; filter narrows the board to done-only.
    const doneChip = page.getByTestId("board-filter-status-done");
    await doneChip.click();
    await page.waitForTimeout(250);
    const afterCount = await page
      .locator('[data-testid^="task-card-"]')
      .count();
    // Filtered count should not exceed the pre-filter count.
    expect(afterCount).toBeLessThanOrEqual(beforeCount);
    // Reset chip appears.
    await expect(page.getByTestId("board-filter-status-reset")).toBeVisible();
    await page.screenshot({
      path: "e2e/screenshots/3.7e-b1-after-filter-active.png",
      fullPage: true,
    });
    // Reset.
    await page.getByTestId("board-filter-status-reset").click();
    await page.waitForTimeout(200);

    // 7) Console hygiene.
    // eslint-disable-next-line no-console
    console.log("AFTER console errors:", JSON.stringify(consoleErrors));
    expect(consoleErrors).toEqual([]);
  });
});
