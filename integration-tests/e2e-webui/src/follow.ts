// Follows the pipeline in the WebUI until it completes, fails, goes idle or runs out of budget. Moved out of the spec
// so the spec stays under the file cap; behaviour unchanged.
import type { Page } from "@playwright/test";
import * as ui from "./driver.js";
import { IDLE_MINUTES, IdleWatch } from "./idle.js";
import { fileActivity, phaseSignature, readRunState } from "./progress.js";
import type { Report } from "./report.js";

const POLL_MS = 15_000;

export async function waitForTask(page: Page, base: string, projectId: string): Promise<string | null> {
  for (let i = 0; i < 40; i += 1) {
    const id = await ui.findTaskId(page.request, base, projectId);
    if (id) return id;
    await page.waitForTimeout(3000);
  }
  return null;
}

export async function follow(page: Page, base: string, projectId: string, projectPath: string, deadline: number, maxMinutes: number, report: Report): Promise<string> {
  const idle = new IdleWatch(IDLE_MINUTES * 60_000);
  let lastPhases = "";
  let boardShot = false;
  const gateState: ui.GateState = { launchPending: false, terminalApprovalMs: 0 };
  while (Date.now() < deadline) {
    const state = readRunState(projectPath);
    const phases = phaseSignature(state);
    if (phases !== lastPhases) {
      lastPhases = phases;
      await report.step(`Phase state: ${phases}`, page);
      if (!boardShot && state.status === "in_progress") {
        boardShot = true;
        const tab = await ui.openBoardTab(page, base, projectId);
        await report.step("Task board with the running pipeline", tab);
        await tab.close();
      }
    }
    if (state.status === "complete" || state.status === "failed") return state.status;
    for (const done of await ui.answerGates(page, gateState)) {
      report.gate(done);
      if (/exemption|safety dialog/i.test(done)) report.escalation(done);
      await report.step(`Gate answered: ${done}`, page);
    }
    const terminal = await page.locator(".xterm-rows").first().innerText({ timeout: 2000 }).catch(() => "");
    if (!idle.observe(`${phases}|${fileActivity(projectPath)}|${terminal.slice(-2000)}`)) {
      const inbox = await page.context().newPage();
      const prompt = await ui.pendingPrompt(inbox, base);
      report.escalation(`No progress for ${IDLE_MINUTES} minutes; pending prompt the spec cannot answer: ${prompt ? "yes (see inbox screenshot)" : "none found in the inbox"}.`);
      await report.step("Idle abort: inbox", inbox);
      await report.step("Idle abort", page, "No new phase, task state, file change or terminal output.");
      return "idle-abort";
    }
    await page.waitForTimeout(POLL_MS);
  }
  report.escalation(`Wall-clock budget of ${maxMinutes} minutes used up.`);
  await report.step("Budget used up", page);
  return "out-of-budget";
}
