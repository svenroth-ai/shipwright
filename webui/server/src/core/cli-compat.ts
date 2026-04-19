/*
 * Claude CLI version gate.
 *
 * MIN_SUPPORTED_CLI is the version at which every Plan D'' architectural
 * assumption was verified by the Sub-iterate 0 PoC (see
 * ~/.claude/plans/external-launch-poc-results.md). Anything older is
 * unverified and should warn loudly via /api/diagnostics.
 */

import { spawnSync, spawn } from "node:child_process";
import { platform } from "node:os";

export const MIN_SUPPORTED_CLI = "2.1.114";
/**
 * Upper-bound is open-ended with a loose major cap. Anthropic bumped the
 * minor from 2.1 → 2.2 freely historically; we trust patch + minor.
 * Major bumps (3.x) MUST re-run the PoC before we lift the cap.
 */
export const MAX_SUPPORTED_CLI_MAJOR = 2;

export interface ClaudeVersionInfo {
  /** Stdout's first line, e.g. `2.1.114 (Claude Code)`. */
  raw: string;
  /** Extracted semver triple if we could parse one; null on garbage. */
  parsed: { major: number; minor: number; patch: number } | null;
  /** True iff parsed >= MIN_SUPPORTED_CLI AND parsed.major <= MAX_SUPPORTED_CLI_MAJOR. */
  supported: boolean;
}

export interface ClaudeVersionProbeDeps {
  claudeBin?: string;
  spawnSync?: typeof spawnSync;
}

/**
 * Synchronous probe for boot-time diagnostic wiring. Uses spawnSync so it
 * can block the very first response without async plumbing. Windows .cmd
 * shim is handled by shell:true when platform is win32.
 */
export function probeClaudeVersion(deps: ClaudeVersionProbeDeps = {}): ClaudeVersionInfo {
  const sync = deps.spawnSync ?? spawnSync;
  const bin = deps.claudeBin ?? resolveClaudeBin();
  if (!bin) {
    return { raw: "", parsed: null, supported: false };
  }
  const isWin = platform() === "win32";
  const result = isWin
    ? sync(`"${bin}"`, ["--version"], { encoding: "utf-8", shell: true })
    : sync(bin, ["--version"], { encoding: "utf-8", shell: false });
  const raw = ((result.stdout ?? "") as string).trim().split(/\r?\n/)[0] ?? "";
  const parsed = parseClaudeVersion(raw);
  const supported = isSupported(parsed);
  return { raw, parsed, supported };
}

export function parseClaudeVersion(raw: string): ClaudeVersionInfo["parsed"] {
  const match = /(\d+)\.(\d+)\.(\d+)/.exec(raw);
  if (!match) return null;
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3], 10),
  };
}

export function isSupported(parsed: ClaudeVersionInfo["parsed"]): boolean {
  if (!parsed) return false;
  if (parsed.major > MAX_SUPPORTED_CLI_MAJOR) return false;
  const min = parseClaudeVersion(MIN_SUPPORTED_CLI);
  if (!min) return false;
  if (parsed.major < min.major) return false;
  if (parsed.major > min.major) return true;
  if (parsed.minor < min.minor) return false;
  if (parsed.minor > min.minor) return true;
  return parsed.patch >= min.patch;
}

/** Resolve an absolute path to the claude CLI. Handles Windows `.cmd` shim. */
export function resolveClaudeBin(): string | null {
  const isWin = platform() === "win32";
  const lookup = isWin ? "where" : "which";
  const r = spawnSync(lookup, ["claude"], { encoding: "utf-8", shell: false });
  const lines = ((r.stdout ?? "") as string)
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (isWin) {
    const dotCmd = lines.find((l) => /\.cmd$/i.test(l));
    if (dotCmd) return dotCmd;
  }
  return lines[0] ?? null;
}

/** Thin async wrapper — same outcome as probeClaudeVersion, non-blocking. */
export async function probeClaudeVersionAsync(
  deps: ClaudeVersionProbeDeps = {},
): Promise<ClaudeVersionInfo> {
  const bin = deps.claudeBin ?? resolveClaudeBin();
  if (!bin) return { raw: "", parsed: null, supported: false };
  const isWin = platform() === "win32";
  return new Promise((resolve) => {
    const p = isWin
      ? spawn(`"${bin}"`, ["--version"], { shell: true })
      : spawn(bin, ["--version"], { shell: false });
    let stdout = "";
    p.stdout?.on("data", (d) => { stdout += d.toString("utf-8"); });
    p.on("close", () => {
      const raw = stdout.trim().split(/\r?\n/)[0] ?? "";
      const parsed = parseClaudeVersion(raw);
      resolve({ raw, parsed, supported: isSupported(parsed) });
    });
    p.on("error", () => resolve({ raw: "", parsed: null, supported: false }));
  });
}
