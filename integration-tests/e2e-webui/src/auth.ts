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

/** Only the auth variable of the chosen source goes to the child processes; a copied login needs none. */
export function authEnv(source: AuthSource, env: NodeJS.ProcessEnv): Record<string, string> {
  if (source === "env token") return { CLAUDE_CODE_OAUTH_TOKEN: env.CLAUDE_CODE_OAUTH_TOKEN ?? "" };
  if (source === "env key") return { ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY ?? "" };
  return {};
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
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  fs.copyFileSync(loginFile(realHome), target);
  // A copy keeps the source mtime on Windows; stamp it now so the stale-copy scrub never mistakes a live copy for an old one.
  const now = new Date();
  fs.utimesSync(target, now, now);
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
    const home = path.join(workdir, entry.name, "home");
    // A link at home/ or home/.claude could point at the real profile: skip such a folder.
    if ([home, path.join(home, ".claude")].some((p) => fs.lstatSync(p, { throwIfNoEntry: false })?.isSymbolicLink())) continue;
    // The login copy and the .claude.json (API-key approval record). A file younger than the run budget may belong to a live run.
    for (const stale of [loginFile(home), path.join(home, ".claude.json")]) {
      if (fs.existsSync(stale) && now - fs.statSync(stale).mtimeMs >= minAgeMs) {
        fs.rmSync(stale, { force: true });
        removed += 1;
      }
    }
  }
  return removed;
}
