// Under `guided` autonomy the gates are AskUserQuestion menus in the embedded terminal (the design review,
// the "commit earlier output first?" question of the boundary check, ...). The WebUI inbox does not list them
// and the agent words them differently on every run. A user answers by pressing Enter on the highlighted
// first option, which is the agent's recommendation; so does the spec, and it records question and option.
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

/** The menu on screen (highlighted first option and the footer), or null. Pure. */
export function readTerminalMenu(terminalText: string): TerminalMenu | null {
  const m = OPTION_ONE.exec(terminalText);
  if (!m || !FOOTER.test(terminalText)) return null;
  const before = terminalText.slice(0, m.index).split("\n").map((l) => l.trim()).filter(Boolean);
  return { question: before.slice(-3).join(" ").slice(-200), option: m[1].trim().slice(0, 80) };
}

export function needsTerminalAnswer(terminalText: string, lastAnsweredMs: number, nowMs: number): boolean {
  return readTerminalMenu(terminalText) !== null && nowMs - lastAnsweredMs > REANSWER_AFTER_MS;
}

/** Presses Enter on the highlighted first option when a menu is on screen; returns what was answered. */
export async function answerTerminalMenu(page: Page, lastAnsweredMs: number): Promise<TerminalMenu | null> {
  const text = await page.locator(".xterm-rows").first().innerText({ timeout: 2000 }).catch(() => "");
  if (!needsTerminalAnswer(text, lastAnsweredMs, Date.now())) return null;
  const menu = readTerminalMenu(text);
  await page.locator(".xterm-helper-textarea").first().focus({ timeout: 5000 });
  await page.keyboard.press("Enter");
  return menu;
}
