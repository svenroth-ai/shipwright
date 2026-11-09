// A forked run (fork/fork_run.py) starts with its first task "awaiting launch" on the board's pipeline card, and no task exists yet.
// A person presses that card's Launch: the WebUI creates the master task, opens its page and hands the start command to the page's
// terminal through sessionStorage. The page reads it once on mount, so the browser must stay on the task page, and the same
// bounded hand-over as after the modal's Launch covers a command that was lost.
import type { Page } from "@playwright/test";
import { taskStateText } from "./driver.js";
import { captureLaunchCommands, ensureLaunched, handOverCommands } from "./launch-recovery.js";

const CARD_LAUNCH = '[data-testid^="master-run-launch-"][data-mode="launch"]:not([data-testid^="master-run-launch-error-"])';

/** Clicks the waiting card's Launch and confirms the master started. Returns false when the board shows no such button. */
export async function launchWaitingTask(page: Page, base: string, step: (title: string, detail?: string) => Promise<void>): Promise<boolean> {
  await page.goto(base);
  const button = page.locator(CARD_LAUNCH).first();
  if (!(await button.waitFor({ state: "visible", timeout: 20_000 }).then(() => true, () => false))) return false;
  const launched = await captureLaunchCommands(page);
  await button.click();
  await page.waitForURL(/\/tasks\/[^/?#]+/, { timeout: 60_000 });
  const taskId = /\/tasks\/([^/?#]+)/.exec(page.url())?.[1] ?? null;
  await step("Fork: the waiting task was launched from the board card", `Master task ${taskId ?? "?"}.`);
  await ensureLaunched({
    readState: () => taskStateText(page.request, base, taskId),
    readTerminal: () => page.locator(".xterm-rows").first().innerText({ timeout: 2000 }).catch(() => ""),
    handOver: () => (taskId ? handOverCommands(page, taskId, launched.get()) : Promise.resolve(false)),
    step: (title, detail) => step(title, detail),
    sleep: (ms) => page.waitForTimeout(ms),
  });
  return true;
}
