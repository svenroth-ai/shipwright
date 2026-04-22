/*
 * Spec 36b — TerminalLaunchButton clipboard contents.
 *
 * The 2.1 TerminalLaunchButton (primary variant in TaskDetail header) writes
 * the platform-appropriate launch command to the clipboard. We assert the
 * clipboard contents include --name with the task title properly quoted.
 *
 * Tricky-char title coverage moves to spec 48 (per plan). This test focuses
 * on the round-trip: button click → clipboard → command shape correct.
 */

import { test, expect } from "@playwright/test";

test.describe("TerminalLaunchButton — clipboard --name shape", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("primary variant copies command including --name '<title>' (PowerShell on Windows-UA)", async ({
    page,
    request,
    context,
  }) => {
    // Force a Windows User-Agent so the component picks the PowerShell form.
    await context.setExtraHTTPHeaders({
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    });

    const create = await request.post("/api/external/tasks", {
      data: { title: "clipboard-name-spec", cwd: "C:/tmp/clipboard-spec" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
    // Iterate 3 section 04 — the old primary `terminal-launch-btn`
    // variant was replaced by the new header CTA which is
    // state-dependent. A `draft` task surfaces `cta-launch-in-terminal`.
    await expect(page.getByTestId("cta-launch-in-terminal")).toBeVisible();

    await page.getByTestId("cta-launch-in-terminal").click();

    // The button's success state surfaces "Copied — paste into terminal".
    await expect(page.getByTestId("cta-launch-in-terminal")).toContainText(
      /Copied/i,
      { timeout: 5000 },
    );

    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboard).toContain("--session-id");
    expect(clipboard).toContain("--name 'clipboard-name-spec'");
    expect(clipboard).toContain("C:/tmp/clipboard-spec");
    // PowerShell command marker.
    expect(clipboard.startsWith("& claude ")).toBe(true);
  });
});
