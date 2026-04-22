/**
 * Iterate 3.7e-b4 — Inbox BEFORE screenshot.
 *
 * Captures the pre-change Inbox (/inbox) so we can diff visually against
 * the 3.7e-b4-after spec. Requires seed-inbox-fixtures.ts to have been run
 * so two project groups are visible.
 */
import { test } from "@playwright/test";

test.describe("3.7e-b4 BEFORE", () => {
  test("Inbox group headers still show the chevron/bullet (pre-color-chip)", async ({
    page,
  }) => {
    await page.goto("/inbox", { waitUntil: "domcontentloaded" });
    // Wait for the loading spinner to disappear + project groups to render
    // (server needs to observe the newly seeded JSONL files).
    await page
      .locator("[data-testid^='inbox-project-group-']")
      .first()
      .waitFor({ state: "visible", timeout: 15000 });
    await page.waitForTimeout(500);

    await page.screenshot({
      path: "e2e/screenshots/3.7e-b4-before-inbox.png",
      fullPage: true,
    });
  });
});
