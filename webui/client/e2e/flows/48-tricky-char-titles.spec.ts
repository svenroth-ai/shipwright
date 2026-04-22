/*
 * Spec 48 — Tricky-character titles round-trip through clipboard correctly.
 *
 * Asserts the launcher's PowerShell escape spec holds end-to-end:
 *   - single quote → ''
 *   - double quote, backtick, dollar, semicolon, &, |, $ — pass through
 *     literally inside single-quoted string
 *   - umlauts, emoji, CJK — pass through as UTF-8
 *
 * The unit smoke test (server) already verifies PowerShell parses the
 * generated literal cleanly. This spec ensures the renamed title makes
 * it from API → clipboard without escape artifacts.
 */

import { test, expect } from "@playwright/test";

test.describe("Tricky-char titles — clipboard round-trip", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("single quotes, dollar, backtick, emoji, umlaut, CJK all preserved", async ({
    page,
    request,
    context,
  }) => {
    await context.setExtraHTTPHeaders({
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    });

    const trickyTitle = `Test's $weird \`title; & 日本語 ä 🚀`;
    const create = await request.post("/api/external/tasks", {
      data: { title: trickyTitle, cwd: "C:/tmp/tricky" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; title: string } };
    expect(task.title).toBe(trickyTitle);

    await page.goto(`/tasks/${task.taskId}`);
    // Iterate 3 section 04 — header CTA replaces TerminalLaunchButton on
    // TaskDetail. A fresh task renders the Launch variant of the CTA.
    await page.getByTestId("cta-launch-in-terminal").click();
    await expect(page.getByTestId("cta-launch-in-terminal")).toContainText(
      /Copied/i,
    );

    const clipboard = await page.evaluate(() => navigator.clipboard.readText());

    // Single quote → '' (PowerShell single-quoted escape).
    expect(clipboard).toContain(`Test''s`);
    // Backtick + $ + ; + & + Unicode pass through inside single quotes.
    expect(clipboard).toContain(`$weird`);
    expect(clipboard).toContain("`title");
    expect(clipboard).toContain(`& 日本語 ä 🚀`);
  });
});
