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

const PROMPT_LINE = /^(?:PS [^>]*>|[$#%>])?\s*$/;

/** "started" once the task left awaiting_external_start or the terminal shows more than shell prompts; else "stalled". */
export function launchVerdict(stateText: string, terminalText: string): "started" | "stalled" {
  const quiet = terminalText.split("\n").map((l) => l.trim()).filter(Boolean).every((l) => PROMPT_LINE.test(l));
  const waiting = stateText === "state awaiting_external_start";
  if (/^state /.test(stateText) && !waiting) return "started";
  return quiet ? "stalled" : "started";
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
      if (launchVerdict(state, terminal) === "started") {
        await w.step(attempt === 1 ? "Launch confirmed" : `Launch confirmed after hand-over ${attempt - 1}`, `${state}; the terminal shows activity or the task left awaiting_external_start.`);
        return;
      }
      if (waited >= windowMs) break;
      await w.sleep(3_000);
    }
    const shown = terminal.trim().slice(-300) || "(empty)";
    if (attempt === attempts) throw new Error(`The launch did not start after ${attempts} tries: ${state}; terminal: ${shown}`);
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
  return true;
}
