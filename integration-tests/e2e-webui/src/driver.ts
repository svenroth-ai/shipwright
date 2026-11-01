// Drives the WebUI like a person: expert project wizard, New pipeline from the task board, gates, preview.
// Test ids are the WebUI's own (checked against the shipwright-webui checkout at authoring time; re-check).
import type { APIRequestContext, Page } from "@playwright/test";
import { answerTerminalMenu } from "./terminal-gate.js";

const ACTIVE_PROJECT_KEY = "webui.activeProjectId";

export async function createProject(page: Page, base: string, name: string, projectPath: string, profile: string): Promise<void> {
  await page.goto(`${base}/projects?new=1`);
  await page.getByTestId("wizard-modal").waitFor({ timeout: 30_000 });
  await page.getByPlaceholder("My Awesome App").fill(name);
  await page.getByPlaceholder(/my-app/).fill(projectPath);
  // Steps: info -> stack profile -> ... -> confirmation. Pick the profile when its card shows, then walk on.
  // The profile list loads after the step opens; picking nothing saves the project as "custom".
  let picked = false;
  for (let i = 0; i < 6; i += 1) {
    const card = page.getByTestId(`stack-profile-card-${profile}`);
    if (!picked && (await page.locator('[data-testid^="stack-profile-card-"]').first().waitFor({ timeout: i === 0 ? 1000 : 20_000 }).then(() => true, () => false))) {
      await card.waitFor({ timeout: 20_000 });
      await card.click();
      picked = true;
    }
    const next = page.getByTestId("wizard-next");
    const label = (await next.textContent())?.trim() ?? "";
    await next.click();
    if (label.startsWith("Create")) break;
  }
  await page.getByTestId("wizard-modal").waitFor({ state: "hidden", timeout: 30_000 });
  const saved = await findProject(page.request, base, projectPath);
  if (saved.profile !== profile) throw new Error(`The project was saved with profile "${saved.profile}", not "${profile}"`);
}

async function findProject(request: APIRequestContext, base: string, projectPath: string): Promise<{ id: string; profile?: string }> {
  const norm = (p: string) => p.replace(/\\/g, "/").replace(/\/$/, "").toLowerCase();
  const res = await request.get(`${base}/api/projects`);
  const body = (await res.json()) as { data?: { id: string; path?: string; profile?: string }[] };
  const hit = (body.data ?? []).find((p) => p.path && norm(p.path) === norm(projectPath));
  if (!hit) throw new Error("The new project is not in the WebUI's project list");
  return hit;
}

export async function findProjectId(request: APIRequestContext, base: string, projectPath: string): Promise<string> {
  return (await findProject(request, base, projectPath)).id;
}

export async function openBoard(page: Page, base: string, projectId: string): Promise<void> {
  await page.addInitScript(([key, id]) => window.localStorage.setItem(key, id), [ACTIVE_PROJECT_KEY, projectId]);
  await page.goto(`${base}/`);
  await page.getByTestId("task-board-page").waitFor({ timeout: 30_000 });
}

/** A second tab on the task board, so a screenshot of the pipeline there does not disturb the task page. */
export async function openBoardTab(page: Page, base: string, projectId: string): Promise<Page> {
  const tab = await page.context().newPage();
  await openBoard(tab, base, projectId);
  return tab;
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

/**
 * The modal only creates the task (state "draft"). The session starts with the green Launch button on the task
 * page, so click it and wait until it is gone, which means the terminal launch was accepted.
 */
export async function startTaskSession(page: Page, onMiss?: (attempt: number) => Promise<void>, waitMs: { first: number; retry: number } = { first: 30_000, retry: 20_000 }): Promise<void> {
  const cta = page.getByTestId("cta-launch-in-terminal");
  // The button can be missing right after the page loads (seen on fresh starts: terminal open at an empty prompt, task
  // still "Awaiting launch"). Reload and look again before giving up; onMiss records what the task looked like.
  // NOT proven by a passing run: the cause of the missing button is unknown, this only gives it two more chances.
  let visible = false;
  for (let attempt = 1; attempt <= 3 && !visible; attempt++) {
    visible = await cta.waitFor({ state: "visible", timeout: attempt === 1 ? waitMs.first : waitMs.retry }).then(() => true, () => false);
    if (!visible) {
      await onMiss?.(attempt).catch(() => undefined); // recording is best effort and must not end the retry
      if (attempt < 3) await page.reload();
    }
  }
  if (!visible) await cta.waitFor({ state: "visible", timeout: 1_000 }); // throws the usual timeout error
  await cta.click();
  await cta.waitFor({ state: "hidden", timeout: 60_000 });
}

/** The task's state as the WebUI lists it (for the report when the launch button is missing); never throws. */
export async function taskStateText(request: APIRequestContext, base: string, taskId: string | null): Promise<string> {
  if (!taskId) return "task id unknown";
  try {
    const res = await request.get(`${base}/api/external/tasks`);
    const body = (await res.json()) as { tasks?: { taskId: string; state?: string }[] };
    const mine = (body.tasks ?? []).find((t) => t.taskId === taskId);
    return mine ? `state ${mine.state ?? "not reported"}` : "task not in the list";
  } catch (error) {
    return `state unreadable (${String((error as Error).message).slice(0, 80)})`;
  }
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
  /** When the design approval menu in the terminal was last answered (ms since epoch, 0 = never). */
  terminalApprovalMs: number;
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
  const menu = await answerTerminalMenu(page, state.terminalApprovalMs);
  if (menu) {
    state.terminalApprovalMs = Date.now();
    done.push(`terminal question answered with its first option "${menu.option}" (${menu.question})`);
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
  // The button reports a failed preview start with an alert; keep its text instead of waiting for a tab that never opens.
  const alerted = new Promise<never>((_, reject) =>
    page.once("dialog", (d) => {
      const message = d.message();
      void d.dismiss().catch(() => undefined);
      reject(new Error(`The preview button reported: ${message}`));
    }));
  alerted.catch(() => undefined);
  const [popup] = await Promise.all([
    Promise.race([page.context().waitForEvent("page", { timeout: 120_000 }), alerted]),
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
