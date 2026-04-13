import type { ChildProcess } from "child_process";
import { spawn as realSpawn } from "child_process";

export type CliCapability = {
  name: "claude";
  available: boolean;
  version?: string;
  path?: string;
  error?: string;
  checkedAt: string;
};

type SpawnFn = (
  cmd: string,
  args: readonly string[],
  opts?: object,
) => ChildProcess;

export interface CapabilityProbeDeps {
  spawn?: SpawnFn;
  timeoutMs?: number;
  platform?: NodeJS.Platform;
}

interface CommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export async function probeClaudeCli(
  deps: CapabilityProbeDeps = {},
): Promise<CliCapability> {
  const spawn = deps.spawn ?? (realSpawn as unknown as SpawnFn);
  const timeoutMs = deps.timeoutMs ?? 2000;
  const platform = deps.platform ?? process.platform;
  const checkedAt = new Date().toISOString();

  let versionResult: CommandResult;
  try {
    versionResult = await runCommand(spawn, "claude", ["--version"], timeoutMs);
  } catch (err) {
    return {
      name: "claude",
      available: false,
      error: formatSpawnError(err),
      checkedAt,
    };
  }

  if (versionResult.exitCode !== 0) {
    return {
      name: "claude",
      available: false,
      error: `claude --version exited with code ${versionResult.exitCode}`,
      checkedAt,
    };
  }

  const versionMatch = versionResult.stdout.match(/(\d+\.\d+\.\d+)/);
  const version = versionMatch?.[1];

  let path: string | undefined;
  try {
    const lookupCmd = platform === "win32" ? "where" : "which";
    const lookup = await runCommand(spawn, lookupCmd, ["claude"], timeoutMs);
    if (lookup.exitCode === 0) {
      const firstLine = lookup.stdout.trim().split(/\r?\n/)[0];
      if (firstLine) path = firstLine;
    }
  } catch {
    // Path lookup is best-effort — the probe already confirmed availability.
  }

  return {
    name: "claude",
    available: true,
    version,
    path,
    checkedAt,
  };
}

function runCommand(
  spawn: SpawnFn,
  cmd: string,
  args: readonly string[],
  timeoutMs: number,
): Promise<CommandResult> {
  return new Promise((resolve, reject) => {
    let stdout = "";
    let stderr = "";
    let settled = false;

    // Windows: claude is usually installed as claude.cmd (npm global shim).
    // Node's spawn with shell:false cannot resolve .cmd files via PATHEXT,
    // so on Windows we need shell:true. Args are hardcoded constants
    // ("claude", "--version", "where", "which") so there is no injection risk.
    const useShell = process.platform === "win32";
    const child = spawn(cmd, args, { shell: useShell });

    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      try {
        child.kill?.();
      } catch {
        // already dead — ignore
      }
      const err: NodeJS.ErrnoException = new Error(
        `${cmd} timed out after ${timeoutMs}ms`,
      );
      err.code = "ETIMEDOUT";
      reject(err);
    }, timeoutMs);

    child.stdout?.on("data", (chunk: Buffer | string) => {
      stdout += typeof chunk === "string" ? chunk : chunk.toString("utf8");
    });
    child.stderr?.on("data", (chunk: Buffer | string) => {
      stderr += typeof chunk === "string" ? chunk : chunk.toString("utf8");
    });
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
    child.on("close", (code: number | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ exitCode: code ?? -1, stdout, stderr });
    });
  });
}

function formatSpawnError(err: unknown): string {
  const code = (err as NodeJS.ErrnoException)?.code;
  if (code === "ENOENT") return "claude CLI not found on PATH";
  if (code === "ETIMEDOUT") return "claude --version timed out after 2s";
  if (code === "EACCES") return "claude CLI is not executable (permission denied)";
  return `claude spawn failed: ${String((err as Error)?.message ?? err)}`;
}
