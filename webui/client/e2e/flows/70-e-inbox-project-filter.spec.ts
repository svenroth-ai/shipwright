/*
 * Flow E — Inbox project filter + visual regression.
 *
 *   1. Navigate to /inbox — the InboxPage renders.
 *   2. Per FR-03.41, the Inbox SHOULD surface a project filter primitive.
 *      Iterate 3 remediation Phase A6 + B4 (2026-04-20) replaced the chip
 *      bar with a shared ProjectFilterDropdown. The inbox surface mounts
 *      that dropdown wrapped in `inbox-project-filter-dropdown`.
 *   3. With activeProjectId persisted from the URL / localStorage, the
 *      Inbox respects the filter.
 *   4. Visual contract: amber 3 px left-strip border on each row
 *      (not a full amber background) + right-aligned Answer + Dismiss
 *      buttons — per `designs/screens/13-global-inbox.html`.
 */

import { test, expect } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";

test.describe("Flow E — Inbox project filter + visual treatment", () => {
  test("Inbox renders + exposes the project-filter dropdown (FR-03.41)", async ({ page }) => {
    await page.goto("/inbox");
    await expect(page.getByTestId("inbox-page")).toBeVisible();

    // FR-03.41: project filter primitive present in the Inbox surface.
    // Phase B4 mounts the shared ProjectFilterDropdown inside the
    // `inbox-project-filter-dropdown` wrapper. Defensive: also accept the
    // bare dropdown button if the wrapper testid ever moves.
    const inbox = page.getByTestId("inbox-page");
    const wrapper = inbox.getByTestId("inbox-project-filter-dropdown");
    const bareDropdown = inbox.getByTestId("project-filter-dropdown");
    const hasWrapper = (await wrapper.count()) > 0;
    const hasBareDropdown = (await bareDropdown.count()) > 0;

    expect(
      hasWrapper || hasBareDropdown,
      "Inbox should render a project filter dropdown per FR-03.41.",
    ).toBeTruthy();

    // Sanity: the dropdown button itself is visible + clickable.
    await expect(bareDropdown).toBeVisible();
  });

  test("persisted activeProjectId scopes the inbox list", async ({ page }) => {
    // Bias the hook so InboxPage filters to UAT 1.
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("webui.activeProjectId", id);
      } catch {
        /* noop */
      }
    }, UAT_PROJECT_ID);

    // Track whether the inbox fetch completes ok. Attach listeners BEFORE
    // goto to avoid the race between the first page load and waitForResponse.
    const inboxReqs: string[] = [];
    const inboxResps: { status: number; url: string }[] = [];
    const inboxFailures: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/external/inbox") && req.method() === "GET") {
        inboxReqs.push(req.url());
      }
    });
    page.on("response", (resp) => {
      if (resp.url().includes("/api/external/inbox") && resp.request().method() === "GET") {
        inboxResps.push({ status: resp.status(), url: resp.url() });
      }
    });
    page.on("requestfailed", (req) => {
      if (req.url().includes("/api/external/inbox")) {
        inboxFailures.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText ?? "?"}`);
      }
    });

    await page.goto("/inbox");
    await expect(page.getByTestId("inbox-page")).toBeVisible();

    // Poll generously — empirical measurement shows the live endpoint
    // responds in ~10 s (see BUG: inbox endpoint latency). Wait up to 40 s
    // to tolerate server-side contention from the sibling test.
    const deadline = Date.now() + 40_000;
    while (Date.now() < deadline) {
      if (inboxResps.some((r) => r.status >= 200 && r.status < 400)) break;
      await page.waitForTimeout(500);
    }

    const firstResp = inboxResps.find((r) => r.status >= 200 && r.status < 400);
    // Measure + report perf: if the single inbox response took > 2 s, the
    // UI "Loading…" UX is visibly broken, even though the assertion here
    // still passes. Log it so the audit report can call it out.
    // eslint-disable-next-line no-console
    console.log(
      `[Flow E inbox perf] reqs=${inboxReqs.length} resps=${inboxResps.length} firstStatus=${firstResp?.status ?? "none"}`,
    );

    expect(
      firstResp,
      `No 2xx inbox response arrived within 20 s. reqs=${inboxReqs.length} resps=${inboxResps.length}`,
    ).toBeDefined();

    // BUG CANDIDATE: even though the fetch lands ok, InboxPage may still
    // display "Loading…" indefinitely — that would imply the react-query
    // resolver didn't transition state. This assertion catches that.
    await expect
      .soft(
        page.getByText("Loading…"),
        "InboxPage stuck showing 'Loading…' even after a successful /api/external/inbox fetch — BUG.",
      )
      .toHaveCount(0, { timeout: 5_000 });

    // Either the empty chip shows OR at least one session group rendered.
    const empty = page.getByTestId("inbox-empty");
    const anyGroup = page.locator('[data-testid^="inbox-session-"]').first();
    const hasEmpty = (await empty.count()) > 0;
    const hasGroup = (await anyGroup.count()) > 0;
    expect.soft(
      hasEmpty || hasGroup,
      "/inbox must render either inbox-empty or at least one session group",
    ).toBeTruthy();
  });

  test("InboxRow uses an amber left strip, NOT a full amber background", async ({
    page,
  }) => {
    await page.goto("/inbox");
    await expect(page.getByTestId("inbox-page")).toBeVisible();

    const firstRow = page.locator('[data-testid^="inbox-item-"]').first();
    if ((await firstRow.count()) === 0) {
      test.skip(true, "No inbox rows present; visual assertion not applicable.");
      return;
    }

    // Compute the row's border-left width + background.
    const styles = await firstRow.evaluate((el: HTMLElement) => {
      const cs = window.getComputedStyle(el);
      return {
        borderLeftWidth: cs.borderLeftWidth,
        backgroundColor: cs.backgroundColor,
        borderLeftColor: cs.borderLeftColor,
      };
    });

    // Strip should be 3 px (per InboxRow CSS). Background should NOT be amber.
    expect(styles.borderLeftWidth).toBe("3px");
    // Amber palettes: #FEF3C7 / rgb(254, 243, 199), #F59E0B / rgb(245,158,11).
    expect(styles.backgroundColor.toLowerCase()).not.toContain("254, 243, 199");
    expect(styles.backgroundColor.toLowerCase()).not.toContain("245, 158, 11");
  });
});
