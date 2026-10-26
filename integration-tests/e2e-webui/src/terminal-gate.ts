// The design review under `guided` autonomy is an AskUserQuestion menu in the embedded terminal, not the
// Mission-view gate card, and the WebUI inbox does not list it. A user answers it by pressing Enter on the
// preselected "Approve screens" option; so does the spec.
import type { Page } from "@playwright/test";

const MENU = /1\.\s*Approve screens/;
const FOOTER = /Enter to select/;
/** After one Enter, stale scrollback must not trigger a second one for this long. */
export const REANSWER_AFTER_MS = 60_000;

export function needsTerminalApproval(terminalText: string, lastAnsweredMs: number, nowMs: number): boolean {
  return MENU.test(terminalText) && FOOTER.test(terminalText) && nowMs - lastAnsweredMs > REANSWER_AFTER_MS;
}

/** Presses Enter on the preselected option when the design approval menu is on screen. */
export async function answerTerminalApproval(page: Page, lastAnsweredMs: number): Promise<boolean> {
  const text = await page.locator(".xterm-rows").first().innerText({ timeout: 2000 }).catch(() => "");
  if (!needsTerminalApproval(text, lastAnsweredMs, Date.now())) return false;
  await page.locator(".xterm-helper-textarea").first().focus({ timeout: 5000 });
  await page.keyboard.press("Enter");
  return true;
}
