/*
 * Phase 3.7d-A foundation verify — screenshots of:
 *   1. TaskBoard + card hover → new Launch/Resume labels.
 *   2. + New wizard modal → "Launch & Copy" CTA.
 *   3. TaskDetail (if live task exists) → new user-bubble color.
 *   4. Settings page → trimmed copy.
 *
 * Non-destructive: uses whatever tasks currently exist. If no tasks,
 * still captures empty TaskBoard + Settings page.
 */
import { test } from "@playwright/test";

test.describe("phase 3.7d-A foundation", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("capture screenshots", async ({ page }) => {
    // 1. TaskBoard — hover to surface the in-progress action row (if any).
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // Give any cards time to render.
    await page.waitForTimeout(500);
    // Hover the first task card if present.
    const firstCard = page.locator('[data-testid^="task-card-"]').first();
    if (await firstCard.count()) {
      await firstCard.hover();
      await page.waitForTimeout(250);
    }
    await page.screenshot({
      path: "e2e/screenshots/phase-3.7d-a-taskboard.png",
      fullPage: true,
    });

    // 2. + New wizard modal. Open via the sidebar split button (default
    //    primary → new-task mode).
    const newBtn = page.getByTestId("create-menu-primary");
    if (await newBtn.count()) {
      await newBtn.click();
      await page.waitForSelector('[data-testid^="new-issue-modal-"]', {
        timeout: 3000,
      });
      await page.waitForTimeout(200);
      await page.screenshot({
        path: "e2e/screenshots/phase-3.7d-a-wizard-modal.png",
        fullPage: true,
      });
      // Close modal for next capture.
      await page.keyboard.press("Escape");
      await page.waitForTimeout(200);
    }

    // 3. TaskDetail — navigate to the first task if any.
    if (await firstCard.count()) {
      await firstCard.click();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(800);
      await page.screenshot({
        path: "e2e/screenshots/phase-3.7d-a-task-detail.png",
        fullPage: true,
      });
    }

    // 4. Settings — trimmed copy.
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: "e2e/screenshots/phase-3.7d-a-settings.png",
      fullPage: true,
    });
  });
});
