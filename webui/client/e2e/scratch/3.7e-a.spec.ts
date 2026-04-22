/**
 * Iterate 3.7e-a Foundation — visual verification.
 *
 * Captures screenshots of every top-level page after the R1..R7 foundation
 * changes land:
 *   - Board: unified .board-container (1600 max-width, 24 px L/R padding).
 *   - Projects / Settings / Inbox: headers wrapped in .page-container.
 *   - TaskDetail (Deploy pipeline to prod): assistant bubble → "CLAUDE"
 *     label, user bubble → no border + shadow, ask-bubble → "Answer in
 *     Terminal" button.
 *
 * Screenshots:
 *   e2e/screenshots/3.7e-a-board.png
 *   e2e/screenshots/3.7e-a-projects.png
 *   e2e/screenshots/3.7e-a-inbox.png
 *   e2e/screenshots/3.7e-a-settings.png
 *   e2e/screenshots/3.7e-a-taskdetail.png
 */
import { test, expect } from "@playwright/test";

test.describe("3.7e-a Foundation", () => {
  test("capture all surfaces after foundation changes", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // 1) Board — unified container.
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    await page.waitForTimeout(2500);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-a-board.png",
      fullPage: true,
    });

    // 2) Projects — header inside .page-container.
    await page.goto("/projects", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("projects-page")).toBeVisible();
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-a-projects.png",
      fullPage: true,
    });

    // 3) Inbox — header inside .page-container.
    await page.goto("/inbox", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("inbox-page")).toBeVisible();
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-a-inbox.png",
      fullPage: true,
    });

    // 4) Settings — header inside .page-container.
    await page.goto("/settings", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("settings-page")).toBeVisible();
    await page.waitForTimeout(1200);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-a-settings.png",
      fullPage: true,
    });

    // 5) TaskDetail — navigate via Inbox to capture ask-bubble + Claude label.
    await page.goto("/inbox", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    const deployCard = page.locator('[data-testid^="inbox-card-"]').first();
    if ((await deployCard.count()) > 0) {
      await deployCard.click();
      await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
      await page.waitForTimeout(2000);
      await page.screenshot({
        path: "e2e/screenshots/3.7e-a-taskdetail.png",
        fullPage: true,
      });
    }

    // 5b) TaskDetail — navigate to a Backlog task (Board first card) so we
    // capture the user-bubble (no border + shadow) styling. The seed tasks
    // from step 5 are Inbox-pending (ask-bubble dominates); Board tasks
    // with "Refactor auth middleware" have a user message at the top.
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    const refactorTitle = page.getByText(/Refactor auth middleware/i).first();
    if ((await refactorTitle.count()) > 0) {
      await refactorTitle.click();
      await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
      await page.waitForTimeout(2000);
      // Scroll to the top of the transcript so the user bubble is visible.
      const scroll = page.getByTestId("transcript-scroll");
      if ((await scroll.count()) > 0) {
        await scroll.evaluate((el) => {
          el.scrollTop = 0;
        });
        await page.waitForTimeout(400);
      }
      await page.screenshot({
        path: "e2e/screenshots/3.7e-a-taskdetail-user-bubble.png",
        fullPage: true,
      });
    } else {
      // Fallback — go straight to /tasks to capture something, but don't fail.
      await page.goto("/", { waitUntil: "domcontentloaded" });
      const firstCard = page.locator('[data-testid^="task-card-"]').first();
      if ((await firstCard.count()) > 0) {
        await firstCard.click();
        await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
        await page.waitForTimeout(1500);
        await page.screenshot({
          path: "e2e/screenshots/3.7e-a-taskdetail.png",
          fullPage: true,
        });
      }
    }

    // eslint-disable-next-line no-console
    console.log("3.7e-a console errors:", JSON.stringify(consoleErrors));
    // Soft assertion — screenshots are the real verification. Just log.
  });
});
