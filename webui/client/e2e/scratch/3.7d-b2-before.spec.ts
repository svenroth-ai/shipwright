/**
 * Iterate 3.7d-b2 — TaskDetail BEFORE screenshots.
 *
 * Opens two seeded TaskDetail screens via direct API lookup (TaskBoard
 * currently crashes due to a parallel agent's Tooltip refactor, so we
 * bypass the board and go straight to /tasks/<id>):
 *   1) "Deploy pipeline to prod" — single pending ask
 *   2) "Add OAuth scope for read:webhooks" — resolved ask + full chat
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
  // Prefer the most-recent task with the given title (seed can be re-run).
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

test.describe("3.7d-b2 BEFORE", () => {
  test("Deploy pipeline — awaiting ask", async ({ page }) => {
    await openTask(page, "Deploy pipeline to prod");
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b2-before-deploy.png",
      fullPage: true,
    });
    // Ask-bubble close-up
    const ask = page.getByTestId("askuser-pending").first();
    if (await ask.count()) {
      await ask.screenshot({ path: "e2e/screenshots/3.7d-b2-before-ask-bubble.png" });
    }
  });

  test("Add OAuth scope — resolved + system toggle", async ({ page }) => {
    await openTask(page, "Add OAuth scope for read:webhooks");
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b2-before-oauth.png",
      fullPage: true,
    });

    // Open 3-dots menu snapshot
    const menu = page.getByTestId("task-detail-menu-trigger");
    if (await menu.isVisible()) {
      await menu.click();
      await page.waitForTimeout(250);
      await page.screenshot({
        path: "e2e/screenshots/3.7d-b2-before-menu.png",
        fullPage: false,
      });
      await page.keyboard.press("Escape");
      await page.waitForTimeout(150);
    }
  });
});
