/**
 * Iterate 3 remediation v2 — Surface 5 (Projects page) BEFORE screenshot.
 *
 * Captures the current (pre-remediation) state of /projects so we can
 * compare against the after screenshot and the 14-projects.html mockup.
 * The Projects page currently wraps its content in `max-w-5xl mx-auto`
 * rather than the Phase-0 `.page-container` utility — this spec does
 * not assert anything about that; it only documents the state.
 */
import { test } from "@playwright/test";

test.describe("iterate-3.7c-5 Surface 5 BEFORE", () => {
  test("projects page current state", async ({ page }) => {
    await page.goto("/projects", { waitUntil: "networkidle" });
    // Wait for either the empty state or at least one card to paint.
    await page
      .waitForSelector('h1:has-text("Projects")', { timeout: 10000 })
      .catch(() => {
        /* tolerate missing — still capture screenshot */
      });
    await page.screenshot({
      path: "e2e/screenshots/surface-5-before.png",
      fullPage: true,
    });
  });
});
