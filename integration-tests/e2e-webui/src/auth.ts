// Claude Code authentication for the temp HOME. Never logs, prints or returns a token or the file content.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export type AuthSource = "env token" | "env key" | "copied login";

export class AuthError extends Error {}

/** Picks the source from the environment only; does not touch the file system for env sources. */
export function pickAuthSource(env: NodeJS.ProcessEnv, realHome: string): AuthSource {
  if ((env.CLAUDE_CODE_OAUTH_TOKEN ?? "").trim() !== "") return "env token";
  if ((env.ANTHROPIC_API_KEY ?? "").trim() !== "") return "env key";
  if (fs.existsSync(loginFile(realHome))) return "copied login";
  throw new AuthError(
    "Refusing to start: no Claude Code authentication. Set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY, " +
      "or log in with Claude Code on this machine so a login file exists in ~/.claude.",
  );
}

export function loginFile(home: string): string {
  return path.join(home, ".claude", ".credentials.json");
}

/** The operator's real home, captured before HOME/USERPROFILE are redirected for the child processes. */
export function realHomeDir(): string {
  return os.homedir();
}

export interface LoginCopy {
  /** Deletes the copy. Safe to call more than once. */
  remove(): void;
}

/** Copies the login file into tempHome/.claude and returns a handle that deletes it again. */
export function copyLogin(realHome: string, tempHome: string): LoginCopy {
  const target = loginFile(tempHome);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(loginFile(realHome), target);
  try {
    fs.chmodSync(target, 0o600);
  } catch {
    // chmod is best effort on Windows
  }
  return {
    remove() {
      fs.rmSync(target, { force: true });
    },
  };
}

/**
 * Deletes login copies left behind by a run that was killed hard (SIGKILL, power loss): the
 * .credentials.json of every run folder (run-STAMP/home/.claude) under the workdir. Only copies older than `minAgeMs` (the run budget) are removed, so a concurrent live run keeps its login. Returns how many were removed.
 */
export function scrubStaleLogins(workdir: string, minAgeMs: number, now: number = Date.now()): number {
  if (!fs.existsSync(workdir)) return 0;
  let removed = 0;
  for (const entry of fs.readdirSync(workdir, { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith("run-")) continue;
    const stale = loginFile(path.join(workdir, entry.name, "home"));
    // A copy younger than the run budget may belong to a run that is still alive (shared default workdir).
    if (fs.existsSync(stale) && now - fs.statSync(stale).mtimeMs >= minAgeMs) {
      fs.rmSync(stale, { force: true });
      removed += 1;
    }
  }
  return removed;
}
