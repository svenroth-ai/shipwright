// The modal's Launch POSTs /launch and hands the start command to the task page through sessionStorage. The page reads that
// key once on mount and the coordinator drops the command after 30 s (or when the terminal is not a writer in time); then the
// task stays "Awaiting launch" at an empty prompt and the page offers NO button (the Launch button exists for drafts only).
// So after the modal launch this module watches for the start, hands the same command over again the way the modal does, and
// fails fast with state and terminal text instead of idling for 20 minutes. WebUI cause: shipwright-webui
// client/src/pages/TaskDetailPage.tsx (mount effect, sessionStorage read once) + contexts/LaunchCoordinatorContext.tsx (30 s expiry).
import type { Page } from "@playwright/test";

export interface LaunchCommands { powershell: string; cmd: string; posix: string }

/** Remembers the commands of the modal's /launch response (the page deletes its own copy when it reads it). */
export function captureLaunchCommands(page: Page): { get: () => LaunchCommands | null } {
  let commands: LaunchCommands | null = null;
  page.on("response", (res) => {
    if (res.request().method() !== "POST" || !/\/api\/external\/tasks\/[^/]+\/launch$/.test(res.url())) return;
    res.json().then((body: { commands?: LaunchCommands }) => { if (body.commands) commands = body.commands; }, () => undefined);
  });
  return { get: () => commands };
}

/**
 * "started" once the task is in a real state other than awaiting_external_start, or the terminal shows the agent (the typed
 * command or its output); else "stalled". Shell banners and prompts (pwsh/cmd/bash) are never evidence of a start, and an
 * unreadable state ("state unreadable (...)", "state not reported") is no evidence either way.
 */
export function launchVerdict(stateText: string, terminalText: string): "started" | "stalled" | "failed" {
  if (/^state (?:failed|launch_failed|jsonl_missing|inactive|cancelled|error)$/.test(stateText)) return "failed";
  if (/^state (?!awaiting_external_start$|not reported$)\w+$/.test(stateText)) return "started";
  return /claude/i.test(terminalText) && !/not recognized|command not found|no such file/i.test(terminalText) ? "started" : "stalled";
}

export interface LaunchWatch {
  readState: () => Promise<string>;
  readTerminal: () => Promise<string>;
  /** Hands the command over once more (sessionStorage + reload); false when there is nothing to hand over. */
  handOver: () => Promise<boolean>;
  step: (title: string, detail: string) => Promise<void>;
  sleep: (ms: number) => Promise<void>;
  windowMs?: number; // how long one attempt may take before it counts as stalled (default 60 s)
  attempts?: number; // launches in total, the modal's included (default 3)
}

/** Resolves when the task started; throws with state and terminal text when the bounded hand-overs did not help. */
export async function ensureLaunched(w: LaunchWatch): Promise<void> {
  const windowMs = w.windowMs ?? 60_000;
  const attempts = w.attempts ?? 3;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    let state = "";
    let terminal = "";
    for (let waited = 0; ; waited += 3_000) {
      state = await w.readState();
      terminal = await w.readTerminal();
      const verdict = launchVerdict(state, terminal);
      if (verdict === "failed") throw new Error(`The task failed to launch: ${state}; terminal: ${terminal.trim().slice(-300) || "(empty)"}`);
      if (verdict === "started") {
        await w.step(attempt === 1 ? "Launch confirmed" : `Launch confirmed after hand-over ${attempt - 1}`, `${state}; the terminal shows activity or the task left awaiting_external_start.`);
        return;
      }
      if (waited >= windowMs) break;
      await w.sleep(3_000);
    }
    const shown = terminal.trim().slice(-300) || "(empty)";
    if (attempt === attempts) throw new Error(`The launch did not start after ${attempts} tries: ${state}; terminal: ${shown}`);
    if (launchVerdict(await w.readState(), await w.readTerminal()) === "started") { // it started while the last poll was read
      await w.step("Launch confirmed", "The task started just before the hand-over; nothing was handed over.");
      return;
    }
    const sent = await w.handOver();
    await w.step(`Launch stalled (attempt ${attempt} of ${attempts})`, `${state}; terminal: ${shown}. ${sent ? "Command handed to the task page again." : "No command captured, nothing to hand over."}`);
    if (!sent) throw new Error(`The launch did not start and no command was captured to retry: ${state}; terminal: ${shown}`);
  }
}

/** Puts the command under the key the modal uses and reloads, so the task page dispatches it on mount. */
export async function handOverCommands(page: Page, taskId: string, commands: LaunchCommands | null): Promise<boolean> {
  if (!commands) return false;
  await page.evaluate(({ key, value }) => window.sessionStorage.setItem(key, value),
    { key: `webui:pending-auto-launch:${taskId}`, value: JSON.stringify({ commands, resume: false, ts: Date.now() }) });
  await page.reload();
  // A pty that survived the reload parks the command behind a "Send to terminal" banner; a person would press it.
  const send = page.getByTestId("embedded-terminal-manual-send-button");
  if (await send.waitFor({ state: "visible", timeout: 5_000 }).then(() => true, () => false)) await send.click();
  return true;
}
