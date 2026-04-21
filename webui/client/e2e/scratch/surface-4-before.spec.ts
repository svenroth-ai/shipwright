/**
 * Iterate 3 remediation v2 — Surface 4 (Inbox) — BEFORE screenshot.
 *
 * Captures the Inbox page in its pre-change state so the agent can diff
 * against the mockup + the `after` screenshot. Not part of any regression
 * suite.
 */
import { test, expect } from "@playwright/test";

test.describe("surface-4 Inbox — before", () => {
  test("capture inbox before screenshot", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.goto("/inbox", { waitUntil: "networkidle" });
    await expect(page.getByTestId("inbox-page")).toBeVisible();

    await page.screenshot({
      path: "e2e/screenshots/surface-4-before.png",
      fullPage: true,
    });

    // Purely diagnostic — log but do not assert (before the change, any
    // existing errors are noise we'll track separately).
    if (consoleErrors.length > 0) {
      console.log("BEFORE console errors:", consoleErrors);
    }
  });
});
