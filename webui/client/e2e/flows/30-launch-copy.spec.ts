/*
 * Spec 30 — Kanban → Task Detail → Launch CTA → clipboard contains
 * pre-bound `--session-id` command + state transitions to
 * `awaiting_external_start`.
 *
 * Iterate 3 section 04 rewrite: the legacy LaunchRow + CopyCommandCard
 * (three rows of PS/cmd/POSIX copy buttons) was deleted. The new
 * TaskDetailHeader renders a single state-dependent CTA
 * `cta-launch-in-terminal` that copies the platform-appropriate command
 * to the clipboard in one shot.
 */

import { test, expect } from "@playwright/test";

test.describe("TaskDetail Launch CTA", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("Launch CTA copies pre-bound command + transitions state", async ({
    page,
    request,
    context,
  }) => {
    await context.setExtraHTTPHeaders({
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    });

    const title = `e2e-launch-${Date.now()}`;
    const create = await request.post("/api/external/tasks", {
      data: { title, cwd: process.cwd() },
    });
    expect(create.status()).toBe(200);
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();
    await expect(page.getByTestId("task-state-badge")).toHaveText("Draft");

    await page.evaluate(() => navigator.clipboard.writeText(""));
    await page.getByTestId("cta-launch-in-terminal").click();

    // iterate 3.9c: after click, state flips draft → awaiting_external_start
    // and cta-launch-in-terminal unmounts. Wait on the badge transition
    // instead of the transient "Copied" label.
    await expect(page.getByTestId("task-state-badge")).toHaveText(
      "Awaiting launch",
      { timeout: 5000 },
    );

    const clipboard = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboard).toMatch(/--session-id '[0-9a-f-]{36}'/);
  });
});
