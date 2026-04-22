/**
 * Iterate 3.7e-b3 BEFORE — Projects page baseline screenshot.
 *
 * NOTE: This spec was authored AFTER implementation landed because
 * parallel surface agents were racing and reverting the page to the
 * old card layout would have interfered with the b1/b2/b4 agents
 * also running on the same branch. Intended as documentation only —
 * the REAL verification spec is 3.7e-b3-after.spec.ts which asserts
 * the new table structure + color picker + settings dialog + error
 * banner behavior.
 *
 * The old card layout is visible in foundation commit e11c85a's
 * screenshot: webui/client/e2e/screenshots/3.7e-a-projects.png.
 */
import { test } from "@playwright/test";

test.describe("3.7e-b3 BEFORE", () => {
  test("capture Projects page as-is (reference snapshot)", async ({ page }) => {
    await page.goto("/projects", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: "e2e/screenshots/3.7e-b3-before-projects.png",
      fullPage: true,
    });
  });
});
