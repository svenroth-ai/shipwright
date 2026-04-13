import { describe, it, expect, vi } from "vitest";
import { EventEmitter, PassThrough } from "stream";
import { probeClaudeCli } from "./capability-probe.js";

function makeChild() {
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const child = new EventEmitter() as any;
  child.stdout = stdout;
  child.stderr = stderr;
  child.kill = vi.fn();
  return { child, stdout, stderr };
}

type Scripted = {
  stdout?: string;
  exitCode?: number | null;
  errorCode?: string;
  neverExits?: boolean;
};

function scriptedSpawn(scripts: Record<string, Scripted>) {
  return (cmd: string, _args: readonly string[]) => {
    const { child, stdout } = makeChild();
    const script = scripts[cmd];
    if (!script) {
      queueMicrotask(() => {
        const err: NodeJS.ErrnoException = new Error(`no script for ${cmd}`);
        err.code = "ENOENT";
        child.emit("error", err);
      });
      return child as any;
    }
    queueMicrotask(() => {
      if (script.errorCode) {
        const err: NodeJS.ErrnoException = new Error(`spawn ${cmd} failed`);
        err.code = script.errorCode;
        child.emit("error", err);
        return;
      }
      if (script.stdout) stdout.write(script.stdout);
      if (script.neverExits) return;
      child.emit("close", script.exitCode ?? 0);
    });
    return child as any;
  };
}

describe("probeClaudeCli", () => {
  it("returns available + version when claude --version succeeds", async () => {
    const spawn = scriptedSpawn({
      claude: { stdout: "1.2.3 (Claude Code)\n", exitCode: 0 },
      where: { stdout: "C:\\Users\\dev\\AppData\\claude.cmd\n", exitCode: 0 },
      which: { stdout: "/usr/local/bin/claude\n", exitCode: 0 },
    });
    const result = await probeClaudeCli({ spawn, platform: "linux" });
    expect(result.available).toBe(true);
    expect(result.version).toBe("1.2.3");
    expect(result.path).toBe("/usr/local/bin/claude");
    expect(result.error).toBeUndefined();
    expect(result.checkedAt).toMatch(/\d{4}-\d{2}-\d{2}T/);
  });

  it("reports ENOENT as not-found on PATH", async () => {
    const spawn = scriptedSpawn({
      claude: { errorCode: "ENOENT" },
    });
    const result = await probeClaudeCli({ spawn });
    expect(result.available).toBe(false);
    expect(result.error).toBe("claude CLI not found on PATH");
    expect(result.version).toBeUndefined();
  });

  it("reports non-zero exit from claude --version as unavailable", async () => {
    const spawn = scriptedSpawn({
      claude: { stdout: "", exitCode: 2 },
    });
    const result = await probeClaudeCli({ spawn });
    expect(result.available).toBe(false);
    expect(result.error).toContain("exited with code 2");
  });

  it("times out cleanly when spawn never exits", async () => {
    const spawn = scriptedSpawn({
      claude: { neverExits: true },
    });
    const result = await probeClaudeCli({ spawn, timeoutMs: 50 });
    expect(result.available).toBe(false);
    expect(result.error).toBe("claude --version timed out after 2s");
  });

  it("still reports available even if path lookup fails", async () => {
    const spawn = scriptedSpawn({
      claude: { stdout: "2.0.0\n", exitCode: 0 },
      // no 'which' / 'where' entry → spawn falls through to ENOENT
    });
    const result = await probeClaudeCli({ spawn, platform: "linux" });
    expect(result.available).toBe(true);
    expect(result.version).toBe("2.0.0");
    expect(result.path).toBeUndefined();
  });

  it("reports available without version when output has no semver", async () => {
    const spawn = scriptedSpawn({
      claude: { stdout: "claude (dev build)\n", exitCode: 0 },
      which: { stdout: "/usr/bin/claude\n", exitCode: 0 },
    });
    const result = await probeClaudeCli({ spawn, platform: "linux" });
    expect(result.available).toBe(true);
    expect(result.version).toBeUndefined();
    expect(result.path).toBe("/usr/bin/claude");
  });
});
