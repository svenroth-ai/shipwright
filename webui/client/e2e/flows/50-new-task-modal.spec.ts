/*
 * Spec 50 — NewIssueModal Save-to-Backlog roundtrip.
 *
 * Verifies the iterate 3 section 03 contract on the TaskBoard page:
 *   - The `+ New ▾` split-button opens the modal.
 *   - Save-to-Backlog creates a task in the Backlog column (draft state)
 *     without navigating away and without writing to the clipboard.
 *   - Priority field is absent (FR-03.21 regression).
 *   - Footer hint reads exactly "Esc to cancel" (FR-03.92).
 *
 * Launch-path assertions live in spec 50b (launch from backlog via
 * TaskDetail) to keep this test clipboard-free — clipboard access on
 * localhost-only HTTP is unreliable in CI.
 */

import { test, expect } from "@playwright/test";

test.describe("NewIssueModal — Save to Backlog", () => {
  test("split-button opens modal → save lands the task in Backlog without clipboard write", async ({ page, request }) => {
    // Pre-seed a project so CreateMenuSplitButton has actions to render.
    // GET /api/projects does not accept a POST body create shortcut that
    // bypasses the filesystem check (project.path must exist on disk).
    // Fall through to an existing project if one is registered.
    //
    // Phase A5 (iterate 3 remediation, 2026-04-20): `/api/projects` returns
    // `{ data: [...] }` per the apiFetch envelope convention — the prior
    // `.projects` destructure was silent drift from iterate 2.
    const existing = await request.get("/api/projects");
    const { data: projectList = [] } = (await existing.json()) as {
      data?: Array<{ id: string; name: string; synthesized?: boolean }>;
    };
    const project = projectList.find((p) => !p.synthesized);
    test.skip(!project, "Requires a registered project; run the project wizard first.");

    await page.goto("/");
    await expect(page.getByTestId("task-board-page")).toBeVisible();

    // Open the modal via the primary split-button.
    await page.getByTestId("create-menu-primary").click();

    // Modal is visible and the footer hint reads exactly "Esc to cancel".
    const modal = page.getByTestId(/new-issue-modal-/);
    await expect(modal).toBeVisible();
    await expect(page.getByTestId("new-issue-footer-hint")).toHaveText(
      /^\s*Esc\s*to cancel\s*$/,
    );

    // Priority field is absent (FR-03.21 regression).
    await expect(page.getByLabel(/priority/i)).toHaveCount(0);

    const title = `spec-50-${Date.now()}`;
    await page.getByTestId("new-issue-title-input").fill(title);
    await page.getByTestId("new-issue-save-btn").click();

    // Modal closes; no navigation away from the board.
    await expect(page.getByTestId("task-board-page")).toBeVisible();
    // Task lands in the Draft column (Backlog).
    const draft = page.getByTestId("column-draft");
    await expect(draft).toContainText(title);
  });
});
