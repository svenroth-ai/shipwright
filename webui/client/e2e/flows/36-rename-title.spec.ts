/*
 * Spec 36 — Title rename via TaskDetail header.
 *
 * Validates the 2.1 rename UX:
 *   - In-place edit on TaskDetail header.
 *   - Reload preserves the new title (PATCH persists to sdk-sessions.json).
 *   - The next launch command picks up the renamed title via --name.
 *
 * Spec 36b (separate test below) covers clipboard contents — the launch
 * button copies a command that contains --name with the renamed title
 * correctly quoted for the host platform.
 */

import { test, expect } from "@playwright/test";

test.describe("TaskDetail title rename + launch sync", () => {
  test("rename in TaskDetail header survives reload + appears in launch command (--name)", async ({
    page,
    request,
  }) => {
    // Seed a task via API so the test isolates from the create-form UI.
    const create = await request.post("/api/external/tasks", {
      data: { title: "before-rename", cwd: "C:/tmp/rename-spec" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; title: string } };
    expect(task.title).toBe("before-rename");

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();

    // Click the title to enter edit mode, type a new value, press Enter.
    await page.getByTestId("task-title-display").click();
    const input = page.getByTestId("task-title-input-edit");
    await expect(input).toBeVisible();
    await input.fill("after-rename");
    await input.press("Enter");

    // Display refreshes to the new title.
    await expect(page.getByTestId("task-title-display")).toHaveText(/after-rename/);

    // Hard-reload: the API GET should return the renamed title.
    await page.reload();
    await expect(page.getByTestId("task-title-display")).toHaveText(/after-rename/);

    // Trigger a launch via the new header CTA (iterate 3 section 04 —
    // LaunchRow / CopyCommandCard deleted). The command is copied to
    // the clipboard; we assert --name carries the renamed title.
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await context.setExtraHTTPHeaders({
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    });
    await page.evaluate(() => navigator.clipboard.writeText(""));
    // Task is now in awaiting_external_start (or later) after the
    // reload-after-rename navigation — the CTA surfaces Resume, not
    // Launch. Both call the same launch endpoint; the result payload
    // embeds --name '<title>' either way.
    const resumeVisible = await page
      .getByTestId("cta-copy-resume-command")
      .isVisible()
      .catch(() => false);
    const ctaTestId = resumeVisible ? "cta-copy-resume-command" : "cta-launch-in-terminal";
    await page.getByTestId(ctaTestId).click();
    await expect(page.getByTestId(ctaTestId)).toContainText(/Copied/i, { timeout: 5000 });
    const ps = await page.evaluate(() => navigator.clipboard.readText());
    expect(ps).toContain("--name 'after-rename'");
    expect(ps).not.toContain("--name 'before-rename'");
  });

  test("rename via Escape cancels without writing", async ({ page, request }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "escape-cancel", cwd: "C:/tmp/rename-cancel" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    await page.goto(`/tasks/${task.taskId}`);
    await page.getByTestId("task-title-display").click();
    const input = page.getByTestId("task-title-input-edit");
    await input.fill("would-be-discarded");
    await input.press("Escape");

    await expect(page.getByTestId("task-title-display")).toHaveText(/escape-cancel/);
  });
});
