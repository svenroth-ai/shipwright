// Under `guided` autonomy the gates are AskUserQuestion menus in the embedded terminal (the design review,
// the "commit earlier output first?" question of the boundary check, the screenshot-check exemption, ...). The
// WebUI inbox does not list them and the agent words them differently on every run. A user answers by pressing
// Enter on the highlighted first option, which is the agent's recommendation; so does the spec, and it records
// what it saw. Long menus scroll their first lines out of the visible rows, so the footer is the signal.
import type { Page } from "@playwright/test";

const OPTION_ONE = /[❯>]\s*1\.\s*(\S[^\n]*)/;
// A menu has the footer; the final page of a multi-question form ("Ready to submit your answers?") has none.
const FOOTER = /Enter to select|Ready to submit your answers/;
/** After one Enter, stale scrollback must not trigger a second one for this long. */
export const REANSWER_AFTER_MS = 15_000;

export interface TerminalMenu {
  question: string;
  option: string;
}

/** The menu on screen (its footer), or null. Pure. */
export function readTerminalMenu(terminalText: string): TerminalMenu | null {
  if (!FOOTER.test(terminalText)) return null;
  const m = OPTION_ONE.exec(terminalText);
  const lines = terminalText.split("\n").map((l) => l.trim()).filter(Boolean);
  const before = m ? terminalText.slice(0, m.index).split("\n").map((l) => l.trim()).filter(Boolean) : lines;
  return {
    question: before.slice(-3).join(" ").slice(-200),
    option: m ? m[1].trim().slice(0, 80) : "(first option; its line is scrolled out of view)",
  };
}

export function needsTerminalAnswer(terminalText: string, lastAnsweredMs: number, nowMs: number): boolean {
  return readTerminalMenu(terminalText) !== null && nowMs - lastAnsweredMs > REANSWER_AFTER_MS;
}

/**
 * The Test phase asks what to do when the screenshot check cannot capture the app: patch the app or the tool
 * (a feature or a weakened security header the brief did not ask for), complete with a recorded exemption, or
 * stop. When the exemption is the SECOND visible option, the spec takes it; when it is first, the plain Enter
 * already does. The report lists it as an escalation: it is a gap in the screenshot check, not a decision of
 * the brief.
 */
export function wantsExemption(terminalText: string): boolean {
  return /2\.\s*Complete with exemption/.test(terminalText) && /Stop the run/.test(terminalText) && FOOTER.test(terminalText);
}

/**
 * Claude Code's own safety dialog ("Dangerous rm operation ... Do you want to proceed? 1. Yes 2. No") also shows
 * under bypassPermissions. It is refused, never approved: the dialog itself tells the agent to rewrite the command
 * safely, and "Yes" would switch the safety net off.
 */
export function isDangerousOperationPrompt(terminalText: string): boolean {
  return /Dangerous [^\n]*operation/i.test(terminalText) && /Do you want to proceed\?/.test(terminalText) && /[❯>]\s*1\.\s*Yes/.test(terminalText);
}

/** Answers the menu on screen, if any; returns what was answered. */
export async function answerTerminalMenu(page: Page, lastAnsweredMs: number): Promise<TerminalMenu | null> {
  const text = await page.locator(".xterm-rows").first().innerText({ timeout: 2000 }).catch(() => "");
  if (Date.now() - lastAnsweredMs <= REANSWER_AFTER_MS) return null;
  const input = page.locator(".xterm-helper-textarea").first();
  if (isDangerousOperationPrompt(text)) {
    await input.focus({ timeout: 5000 });
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    return { question: "Claude Code safety dialog: dangerous operation", option: "No (refused; the agent rewrites the command)" };
  }
  if (wantsExemption(text)) {
    await input.focus({ timeout: 5000 });
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    return { question: "Test phase: screenshot check cannot capture the app", option: "Complete with exemption (plugin gap, recorded as an escalation)" };
  }
  const menu = readTerminalMenu(text);
  if (!menu) return null;
  await input.focus({ timeout: 5000 });
  await page.keyboard.press("Enter");
  return menu;
}
