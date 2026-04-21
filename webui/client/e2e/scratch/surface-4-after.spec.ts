/**
 * Iterate 3 remediation v2 — Surface 4 (Inbox) — AFTER browser-verify.
 *
 * Walks the user journey on the redesigned Inbox:
 *   - `ProjectFilterDropdown` mount is gone
 *   - project-group headers render with a `<details open>` wrapper when
 *     the inbox has items
 *   - each card carries Launch + Copy-Resume buttons on the top row
 *   - option pills render as clipboard prefill shortcuts
 *   - no Answer / Dismiss / "best-effort" surfaces
 *   - clicking an option pill invokes the clipboard helper without
 *     crashing
 *   - toggling a `<details>` open/closed state works
 *   - no console errors
 *   - final full-page screenshot for commit traceability
 *
 * This spec tolerates an empty Inbox (dev environment may have none of
 * the three hooks returning rows). It hard-asserts the v2 invariants
 * that do NOT depend on data (no filter dropdown, no answer/dismiss/
 * best-effort surfaces) and soft-asserts the data-dependent invariants.
 */
import { test, expect } from "@playwright/test";

test.describe("surface-4 Inbox — after (redesign)", () => {
  test("inbox renders grouped-by-project with TaskCard CTA parity", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);

    // Use domcontentloaded because the page polls the Inbox endpoint
    // continuously; networkidle never settles.
    await page.goto("/inbox", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("inbox-page")).toBeVisible({ timeout: 15000 });

    // Give the three TanStack Query hooks (inbox, tasks, projects) a
    // chance to resolve so project-groups can render. In a fresh dev
    // environment with an empty inbox, we fall through to the empty
    // state.
    await page
      .waitForSelector(
        '[data-testid^="inbox-project-group-"], [data-testid="inbox-empty"]',
        { timeout: 15000 },
      )
      .catch(() => {
        /* if nothing mounted, the hard assertions below still run */
      });

    // --- Hard invariant 1: the v1 filter dropdown is gone --------------
    await expect(
      page.getByTestId("inbox-project-filter-dropdown"),
    ).toHaveCount(0);

    // --- Hard invariant 2: no Answer / Dismiss / best-effort surfaces --
    await expect(page.locator('[data-testid^="answer-"]')).toHaveCount(0);
    await expect(page.locator('[data-testid^="dismiss-"]')).toHaveCount(0);
    await expect(page.locator("text=/best-?effort/i")).toHaveCount(0);

    // --- Soft invariants (data-dependent): when at least one group
    //     rendered, we check the redesign shape. Otherwise we skip
    //     gracefully. ----------------------------------------------------
    const groups = page.locator('[data-testid^="inbox-project-group-"]');
    const groupCount = await groups.count();

    if (groupCount > 0) {
      // Each card carries both Launch + Copy-Resume buttons.
      const launchButtons = page.locator('[data-testid^="inbox-launch-"]');
      const resumeButtons = page.locator('[data-testid^="inbox-copy-resume-"]');
      const launchCount = await launchButtons.count();
      const resumeCount = await resumeButtons.count();
      expect(launchCount).toBeGreaterThan(0);
      expect(resumeCount).toBe(launchCount);

      // Click an option pill if any, to prove clipboard handler fires.
      const optionPills = page.locator('[data-testid^="inbox-option-"]');
      if ((await optionPills.count()) > 0) {
        await optionPills.first().click();
        await expect(
          page.getByText(/Copied/i).first(),
        ).toBeVisible({ timeout: 2500 });
      }

      // Toggle collapse/expand on the first group.
      const firstGroup = groups.first();
      const toggleSummary = firstGroup.locator("summary").first();
      await toggleSummary.click();
      await page.waitForTimeout(150);
      const collapsed = await firstGroup.evaluate(
        (el) => (el as HTMLDetailsElement).open,
      );
      expect(collapsed).toBe(false);
      await toggleSummary.click();
      await page.waitForTimeout(150);
      const expanded = await firstGroup.evaluate(
        (el) => (el as HTMLDetailsElement).open,
      );
      expect(expanded).toBe(true);
    } else {
      // Inbox is empty in this environment — acceptable. Log and
      // continue.
      console.log(
        "[surface-4-after] inbox had no project groups; data-dependent checks skipped",
      );
    }

    // --- Full-page screenshot for traceability -------------------------
    await page.screenshot({
      path: "e2e/screenshots/surface-4-after.png",
      fullPage: true,
    });

    // --- No console errors during the walk ------------------------------
    expect(consoleErrors).toEqual([]);
  });
});
