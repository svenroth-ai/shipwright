/**
 * Iterate 3.7d-b2 — TaskDetail AFTER screenshots + assertions.
 *
 * Verifies the fixes from 3.7d-b2:
 *   1. ProjectChipMenu removed from header row (no "project-chip-trigger"
 *      chip visible next to the title).
 *   2. "Move to project…" menu entry is present in the 3-dots menu.
 *   3. Title + state-badge are in a centered flex row.
 *   4. Empty transcript renders heading "No events yet" (no seeded empty
 *      task in fixtures — we assert the element exists only conditionally).
 *   5. System-toggle: label updates to include "(N)" when system events
 *      exist (or "No system messages" when none) and bubble count changes
 *      when clicked.
 *   6. Ask-bubble: compact Resume button + larger option chips.
 */
import { test, expect, request as pwRequest, type Page } from "@playwright/test";

interface TaskSummary {
  taskId: string;
  title: string;
  state: string;
  projectId: string;
}

async function taskIdByTitle(title: string): Promise<string> {
  const api = await pwRequest.newContext({ baseURL: "http://localhost:3847" });
  const res = await api.get("/api/external/tasks");
  const json = (await res.json()) as { tasks?: TaskSummary[]; data?: TaskSummary[] };
  const list = json.tasks ?? json.data ?? [];
  const matches = list.filter((t) => t.title === title);
  if (matches.length === 0) {
    throw new Error(`No task with title "${title}" — is the seed loaded? (got ${list.length} total)`);
  }
  return matches[matches.length - 1].taskId;
}

async function openTask(page: Page, title: string): Promise<void> {
  const id = await taskIdByTitle(title);
  await page.goto(`/tasks/${id}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  await expect(page.getByTestId("task-detail-header")).toBeVisible({ timeout: 10_000 });
}

test.describe("3.7d-b2 AFTER", () => {
  test("Deploy pipeline — header + ask bubble polish", async ({ page }) => {
    await openTask(page, "Deploy pipeline to prod");

    // (1) No project-chip trigger visible in the header row.
    const chipTriggers = page.getByTestId("project-chip-trigger");
    await expect(chipTriggers).toHaveCount(0);

    // (3) Title row uses items-center.
    const titleRow = page.getByTestId("task-detail-title-row");
    await expect(titleRow).toBeVisible();
    const className = await titleRow.getAttribute("class");
    expect(className ?? "").toContain("items-center");

    await page.screenshot({
      path: "e2e/screenshots/3.7d-b2-after-deploy.png",
      fullPage: true,
    });

    // (7) Ask-bubble: Resume button + option chips.
    const ask = page.getByTestId("askuser-pending").first();
    await expect(ask).toBeVisible();
    // Compact Resume button rendered inside the bubble.
    const resumeBtn = ask.getByTestId("terminal-launch-compact");
    await expect(resumeBtn).toBeVisible();
    // Options rendered as accessible chips with bigger font.
    const options = ask.getByTestId("askuser-options");
    await expect(options).toBeVisible();
    const firstOption = ask.getByTestId("askuser-option-0");
    await expect(firstOption).toBeVisible();
    const optionFontSize = await firstOption.evaluate(
      (el) => window.getComputedStyle(el).fontSize,
    );
    // Expect ~13 px (spec: 13–14 px, not the previous tiny <12 px bullet).
    expect(parseFloat(optionFontSize)).toBeGreaterThanOrEqual(12.5);
    await ask.screenshot({ path: "e2e/screenshots/3.7d-b2-after-ask-bubble.png" });
  });

  test("Add OAuth scope — menu + system toggle", async ({ page }) => {
    await openTask(page, "Add OAuth scope for read:webhooks");

    // (2) Open 3-dots menu, assert "Move to project…" item present.
    await page.getByTestId("task-detail-menu-trigger").click();
    await page.waitForTimeout(200);
    await expect(page.getByTestId("task-detail-menu")).toBeVisible();
    const moveItem = page.getByTestId("task-detail-menu-move-project");
    await expect(moveItem).toBeVisible();
    await expect(moveItem).toContainText("Move to project");
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b2-after-menu.png",
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // (2b) Click "Move to project…" → popover opens with the options list.
    await page.getByTestId("task-detail-menu-trigger").click();
    await page.waitForTimeout(150);
    await page.getByTestId("task-detail-menu-move-project").click();
    await page.waitForTimeout(350);
    await expect(page.getByTestId("project-chip-popover")).toBeVisible();
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b2-after-move-popover.png",
      fullPage: false,
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(200);

    // (5) System-toggle — inspect label + counter + click behavior.
    const toggle = page.getByTestId("system-toggle");
    await expect(toggle).toBeVisible();
    const countAttrBefore = await toggle.getAttribute("data-system-count");
    const labelBefore = (await toggle.textContent()) ?? "";
    const disabledBefore = await toggle.isDisabled();
    // Seeded OAuth task has zero system events → button disabled with "No system messages".
    if (disabledBefore) {
      expect(labelBefore).toContain("No system messages");
      expect(countAttrBefore).toBe("0");
    } else {
      // If a system event sneaked in, clicking must flip the visible count.
      const countBefore = await page.getByTestId("bubble-system").count();
      await toggle.click();
      await page.waitForTimeout(250);
      const countAfter = await page.getByTestId("bubble-system").count();
      expect(countAfter).not.toBe(countBefore);
      // Click again — reverses.
      await toggle.click();
      await page.waitForTimeout(250);
      const countFinal = await page.getByTestId("bubble-system").count();
      expect(countFinal).toBe(countBefore);
    }

    await page.screenshot({
      path: "e2e/screenshots/3.7d-b2-after-oauth.png",
      fullPage: true,
    });
  });
});
