/*
 * Spec 43 — TerminalLaunchButton variant consistency.
 *
 * Each variant emits the same launch command for a given task; only the
 * interaction differs. Compact (TaskBoard card) = click → copy. Primary
 * (TaskDetail header) = click → copy + announce. Inline (Inbox row) =
 * click → navigate to TaskDetail.
 *
 * The shared command is ensured by every variant going through the
 * /api/external/tasks/:id/launch endpoint and reading the same PowerShell
 * (Windows-UA) form.
 */

import { test, expect } from "@playwright/test";

test.describe("TerminalLaunchButton — variant consistency", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("compact (TaskBoard) and primary (TaskDetail) emit identical launch commands", async ({
    page,
    request,
    context,
  }) => {
    await context.setExtraHTTPHeaders({
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    });

    // Use a unique title so we can't see a leftover clipboard from
    // another spec while polling.
    const uniqueTitle = `variant-spec-${Date.now()}`;
    const create = await request.post("/api/external/tasks", {
      data: { title: uniqueTitle, cwd: "C:/tmp/variant" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    // Compact variant — TaskBoard card. Navigate first so navigator
    // is defined, then clear the clipboard before clicking.
    await page.goto("/");
    await page.evaluate(() => navigator.clipboard.writeText(""));
    const compact = page
      .getByTestId(`task-card-${task.taskId}`)
      .getByTestId("terminal-launch-compact");
    await expect(compact).toBeVisible({ timeout: 5000 });
    await compact.click();

    // Mutation is async; poll the clipboard up to 5 s for OUR specific
    // launch command to land. The compact variant has no visible
    // "Copied" state, so we look for the unique title.
    let compactClip = "";
    await expect(async () => {
      compactClip = await page.evaluate(() => navigator.clipboard.readText());
      expect(compactClip).toContain(`--name '${uniqueTitle}'`);
    }).toPass({ timeout: 5000 });
    // Compact = first launch on a draft task → fresh start, --session-id present.
    expect(compactClip).toContain("--session-id");
    expect(compactClip).not.toContain("--resume");

    // Primary variant — TaskDetail header. Iterate 3 section 04 replaced
    // the old `terminal-launch-btn` with the state-dependent CTA. Post
    // first-launch the task is in awaiting_external_start (or later), so
    // the CTA surfaces as "Copy Resume Command".
    await page.evaluate(() => navigator.clipboard.writeText(""));
    await page.goto(`/tasks/${task.taskId}`);
    // Wait for one of the two CTA variants to land.
    await page.waitForSelector(
      '[data-testid="cta-copy-resume-command"], [data-testid="cta-launch-in-terminal"]',
      { timeout: 5000 },
    );
    const primaryTestId = (await page
      .getByTestId("cta-copy-resume-command")
      .isVisible()
      .catch(() => false))
      ? "cta-copy-resume-command"
      : "cta-launch-in-terminal";
    const primary = page.getByTestId(primaryTestId);
    await primary.click();
    await expect(primary).toContainText(/Copied/i);

    const primaryClip = await page.evaluate(() => navigator.clipboard.readText());
    // Primary = second launch on the same task; state has transitioned past
    // draft, so this is a resume command (--resume <uuid>, no --session-id).
    // The CLI rejects --session-id + --resume together (without --fork-session).
    expect(primaryClip).toContain("--resume");
    expect(primaryClip).not.toContain("--session-id");
    expect(primaryClip).toContain(`--name '${uniqueTitle}'`);

    // The two clipboards target the SAME session UUID — once via
    // --session-id (fresh), once via --resume (re-attach).
    const compactUuidRe = /--session-id '([0-9a-f-]{36})'/;
    const primaryUuidRe = /--resume '([0-9a-f-]{36})'/;
    expect(compactUuidRe.exec(compactClip)?.[1]).toBe(primaryUuidRe.exec(primaryClip)?.[1]);
  });
});
