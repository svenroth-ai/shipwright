/*
 * External-launch copy-command generator.
 *
 * Produces per-shell command strings for the user to paste. Webui does
 * NOT spawn claude; the user runs it themselves so that subscription-auth,
 * plugin-dir discovery, and terminal UX stay Anthropic's problem.
 *
 * Three forms are produced regardless of host OS so the UI can offer
 * the right button set. PoC check G proved all three run cleanly across
 * real PowerShell / cmd.exe / bash with a `"AI Backup - Documents"` path.
 *
 * Terminal / VSCode / Desktop launchers are explicitly deferred to v2+
 * (variant-a narrow scope). The `LaunchAdapter` shape is kept so Sub-iterate
 * 2 can plug implementations in without rewiring callers.
 */

export interface CopyCommandForms {
  powershell: string;
  cmd: string;
  posix: string;
}

export interface LaunchArgs {
  sessionUuid: string;
  cwd: string;
  resume?: boolean;
  fork?: boolean;
  parentSessionUuid?: string;
  pluginDirs?: string[];
}

export interface LaunchResult {
  /** Always populated; the user's fallback. */
  commands: CopyCommandForms;
  /** Future: terminal spawn pid, VSCode binding token, etc. */
  launcherUsed: "copy";
}

export type LaunchAdapter = (args: LaunchArgs) => Promise<LaunchResult> | LaunchResult;

export function buildCopyCommands(args: LaunchArgs): CopyCommandForms {
  const parts = buildArgv(args);
  return {
    powershell: renderPowershell(parts),
    cmd: renderCmd(parts),
    posix: renderPosix(parts),
  };
}

export const copyLauncher: LaunchAdapter = (args) => ({
  commands: buildCopyCommands(args),
  launcherUsed: "copy",
});

// ---------- internal ----------

interface Argv {
  sessionUuid: string;
  cwd: string;
  resume: boolean;
  fork: boolean;
  parentSessionUuid?: string;
  pluginDirs: string[];
}

function buildArgv(args: LaunchArgs): Argv {
  return {
    sessionUuid: args.sessionUuid,
    cwd: args.cwd,
    resume: Boolean(args.resume),
    fork: Boolean(args.fork),
    parentSessionUuid: args.parentSessionUuid,
    pluginDirs: args.pluginDirs ?? [],
  };
}

function renderPowershell(a: Argv): string {
  const parts: string[] = ["claude", "--session-id", qPs(a.sessionUuid), "--add-dir", qPs(a.cwd)];
  appendResumeFork(a, parts, qPs);
  for (const d of a.pluginDirs) {
    parts.push("--plugin-dir", qPs(d));
  }
  return "& " + parts.join(" ");
}

function renderCmd(a: Argv): string {
  const parts: string[] = ["claude", "--session-id", qCmd(a.sessionUuid), "--add-dir", qCmd(a.cwd)];
  appendResumeFork(a, parts, qCmd);
  for (const d of a.pluginDirs) {
    parts.push("--plugin-dir", qCmd(d));
  }
  return parts.join(" ");
}

function renderPosix(a: Argv): string {
  const cwd = toPosixPath(a.cwd);
  const plugins = a.pluginDirs.map(toPosixPath);
  const parts: string[] = ["claude", "--session-id", qPosix(a.sessionUuid), "--add-dir", qPosix(cwd)];
  appendResumeFork(a, parts, qPosix);
  for (const d of plugins) {
    parts.push("--plugin-dir", qPosix(d));
  }
  return parts.join(" ");
}

function appendResumeFork(a: Argv, parts: string[], q: (v: string) => string): void {
  if (a.fork) {
    // fork-session starts a new session derived from a parent; requires a parent UUID.
    if (!a.parentSessionUuid) {
      throw new Error("fork=true requires parentSessionUuid");
    }
    parts.push("--resume", q(a.parentSessionUuid), "--fork-session");
  } else if (a.resume) {
    parts.push("--resume", q(a.sessionUuid));
  }
}

// --- shell-specific escaping ---

function qPs(v: string): string {
  // PS single-quoted: embedded `'` → `''`.
  return `'${v.replace(/'/g, "''")}'`;
}

function qCmd(v: string): string {
  // cmd.exe double-quoted: embedded `"` → `\"`. We do NOT worry about
  // trailing-backslash-before-quote since real inputs (paths, UUIDs, dirs)
  // never end on `\`.
  return `"${v.replace(/"/g, '\\"')}"`;
}

function qPosix(v: string): string {
  // POSIX single-quoted: `'` → `'\''`.
  return `'${v.replace(/'/g, "'\\''")}'`;
}

function toPosixPath(p: string): string {
  return p.replace(/\\/g, "/");
}
