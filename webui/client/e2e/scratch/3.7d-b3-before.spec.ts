/**
 * Iterate 3.7d-b3 — Inbox BEFORE screenshot.
 *
 * Captures the pre-change Inbox (/inbox) so we can diff visually against the
 * 3.7d-b3-after spec. Requires seed-inbox-fixtures.ts to have been run.
 */
import { test } from "@playwright/test";

test.describe("3.7d-b3 BEFORE", () => {
  test("Inbox with 4 pending items under 2 project groups", async ({ page }) => {
    await page.goto("/inbox", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    await page.screenshot({
      path: "e2e/screenshots/3.7d-b3-before-inbox.png",
      fullPage: true,
    });
  });
});
