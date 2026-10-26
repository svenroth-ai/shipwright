// Drives the WebUI like a person: expert project wizard, New pipeline from the task board, gates, preview.
// Test ids are the WebUI's own (checked against the shipwright-webui checkout at authoring time; re-check).
import type { APIRequestContext, Page } from "@playwright/test";

const ACTIVE_PROJECT_KEY = "webui.activeProjectId";

export async function createProject(page: Page, base: string, name: string, projectPath: string, profile: string): Promise<void> {
  await page.goto(`${base}/projects?new=1`);
  await page.getByTestId("wizard-modal").waitFor({ timeout: 30_000 });
  await page.getByPlaceholder("My Awesome App").fill(name);
  await page.getByPlaceholder(/my-app/).fill(projectPath);
  // Steps: info -> stack profile -> ... -> confirmation. Pick the profile when its card shows, then walk on.
  for (let i = 0; i < 6; i += 1) {
    const card = page.getByTestId(`stack-profile-card-${profile}`);
    if (await card.isVisible().catch(() => false)) await card.click();
    const next = page.getByTestId("wizard-next");
    const label = (await next.textContent())?.trim() ?? "";
    await next.click();
    if (label.startsWith("Create")) break;
  }
  await page.getByTestId("wizard-modal").waitFor({ state: "hidden", timeout: 30_000 });
}

export async function findProjectId(request: APIRequestContext, base: string, projectPath: string): Promise<string> {
  const norm = (p: string) => p.replace(/\\/g, "/").replace(/\/$/, "").toLowerCase();
  const res = await request.get(`${base}/api/projects`);
  const body = (await res.json()) as { data?: { id: string; path?: string }[] };
  const hit = (body.data ?? []).find((p) => p.path && norm(p.path) === norm(projectPath));
  if (!hit) throw new Error("The new project is not in the WebUI's project list");
  return hit.id;
}

export async function openBoard(page: Page, base: string, projectId: string): Promise<void> {
  await page.addInitScript(([key, id]) => window.localStorage.setItem(key, id), [ACTIVE_PROJECT_KEY, projectId]);
  await page.goto(`${base}/`);
  await page.getByTestId("task-board-page").waitFor({ timeout: 30_000 });
}

/** Start a "New pipeline" task from the board; the description hands over the package directory. */
export async function startPipeline(page: Page, title: string, description: string): Promise<void> {
  await page.getByTestId("create-menu-caret").click();
  await page.getByTestId("create-menu-item-new-pipeline").click();
  await page.getByTestId("new-issue-modal-new-pipeline").waitFor();
  const titleInput = page.getByTestId("new-issue-title-input");
  if (await titleInput.count()) await titleInput.fill(title);
  await page.getByTestId("new-issue-description-input").fill(description);
}

export async function launchPipeline(page: Page): Promise<void> {
  await page.getByTestId("new-issue-launch-btn").click();
}

export async function findTaskId(request: APIRequestContext, base: string, projectId: string): Promise<string | null> {
  const res = await request.get(`${base}/api/external/tasks`);
  const body = (await res.json()) as { tasks?: { taskId: string; projectId?: string }[] };
  const mine = (body.tasks ?? []).filter((t) => t.projectId === projectId);
  return mine.length > 0 ? mine[mine.length - 1].taskId : null;
}

const seen = (page: Page, id: string, ms: number) =>
  page.getByTestId(id).waitFor({ state: "visible", timeout: ms }).then(() => true, () => false);
const gone = (page: Page, id: string, ms: number) =>
  page.getByTestId(id).waitFor({ state: "hidden", timeout: ms }).then(() => true, () => false);

export interface GateState {
  /** A "next phase" launch was clicked and its button has not gone away yet: never click it again. */
  launchPending: boolean;
}

/**
 * One pass of what a user does at a gate: approve the design review, launch the next phase. Returns what
 * was done, recorded only after the click really happened.
 */
export async function answerGates(page: Page, state: GateState): Promise<string[]> {
  const done: string[] = [];
  if (await seen(page, "design-gate-approve", 1000)) {
    await page.getByTestId("design-gate-approve").click();
    if (await seen(page, "design-gate-approve-confirm", 3000)) {
      await page.getByTestId("design-gate-approve-confirm").click();
      done.push("design review approved");
    } else if (await gone(page, "design-gate-approve", 5000)) {
      done.push("design review approved (no confirmation dialog)");
    }
  }
  if (state.launchPending && (await gone(page, "continue-pipeline-launch-btn", 1000))) state.launchPending = false;
  if (!state.launchPending && (await seen(page, "continue-pipeline-launch-btn", 1000))) {
    await page.getByTestId("continue-pipeline-launch-btn").click();
    done.push("launched the next pipeline phase");
    state.launchPending = !(await gone(page, "continue-pipeline-launch-btn", 30_000));
  }
  return done;
}

/** Opens the app through the project's preview button (a new tab); returns that tab. */
export async function openPreview(page: Page): Promise<Page> {
  page.on("dialog", (d) => void d.dismiss().catch(() => undefined));
  const [popup] = await Promise.all([
    page.context().waitForEvent("page", { timeout: 120_000 }),
    page.getByTestId("preview-button").click(),
  ]);
  await popup.waitForLoadState("domcontentloaded");
  return popup;
}

/**
 * The distinct pending-prompt signal: the WebUI inbox lists AskUserQuestion prompts the spec cannot answer.
 * (Tool-permission prompts are terminal dialogs and do not show here; the permission mode is the guard for those.)
 */
export async function pendingPrompt(inboxPage: Page, base: string): Promise<boolean> {
  try {
    await inboxPage.goto(`${base}/inbox`);
    await inboxPage.getByTestId("inbox-page").waitFor({ timeout: 10_000 });
    await inboxPage.waitForTimeout(1000);
    return (await inboxPage.getByTestId("inbox-empty").count()) === 0;
  } catch {
    return false;
  }
}
