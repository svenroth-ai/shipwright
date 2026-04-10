import { describe, it, expect, vi } from "vitest";
import { ClaudeAdapter } from "./claude-adapter.js";
import type { ClaudeSpawnOptions, SpawnDeps } from "./claude-adapter.js";
import { EventEmitter, PassThrough } from "stream";

function createFakeChild() {
  const stdin = new PassThrough();
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const child = new EventEmitter() as any;
  child.stdin = stdin;
  child.stdout = stdout;
  child.stderr = stderr;
  child.pid = 12345;
  child.kill = vi.fn();
  return { child, stdin, stdout, stderr };
}

function createMockDeps(child: any): SpawnDeps {
  return { spawn: vi.fn(() => child) };
}

const baseOptions: ClaudeSpawnOptions = {
  projectDir: "/tmp/project",
  projectId: "p1",
  taskId: "t1",
  sessionId: "s1",
  resume: false,
  pluginDirs: ["/plugins/a", "/plugins/b"],
  prompt: "Fix the bug",
};

describe("ClaudeAdapter", () => {
  it("parses NDJSON lines from stdout and calls onEvent", async () => {
    const { child, stdout } = createFakeChild();
    const deps = createMockDeps(child);
    const events: any[] = [];
    const adapter = new ClaudeAdapter(deps, (taskId, msg) => events.push({ taskId, msg }));

    adapter.spawn(baseOptions);
    stdout.write(JSON.stringify({ type: "assistant", content: "Hello" }) + "\n");
    stdout.write(JSON.stringify({ type: "tool_use", tool_name: "Bash" }) + "\n");

    await new Promise((r) => setTimeout(r, 10));
    expect(events).toHaveLength(2);
    expect(events[0].msg.type).toBe("assistant");
    expect(events[1].msg.type).toBe("tool_use");
  });

  it("skips malformed NDJSON lines", async () => {
    const { child, stdout } = createFakeChild();
    const deps = createMockDeps(child);
    const events: any[] = [];
    const adapter = new ClaudeAdapter(deps, (_, msg) => events.push(msg));

    adapter.spawn(baseOptions);
    stdout.write("NOT JSON\n");
    stdout.write(JSON.stringify({ type: "assistant", content: "OK" }) + "\n");

    await new Promise((r) => setTimeout(r, 10));
    expect(events).toHaveLength(1);
  });

  it("transitions state from spawning to running on first stdout data", async () => {
    const { child, stdout } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});

    const proc = adapter.spawn(baseOptions);
    expect(proc.state).toBe("spawning");

    stdout.write(JSON.stringify({ type: "assistant", content: "hi" }) + "\n");
    await new Promise((r) => setTimeout(r, 10));
    expect(proc.state).toBe("running");
  });

  it("captures exit code on process close", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});

    const proc = adapter.spawn(baseOptions);
    child.emit("close", 1);
    expect(proc.state).toBe("exited");
    expect(proc.exitCode).toBe(1);
  });

  it("sendStdin writes to stdin pipe", () => {
    const { child, stdin } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    const proc = adapter.spawn(baseOptions);
    proc.state = "running";

    const chunks: string[] = [];
    stdin.on("data", (d: Buffer) => chunks.push(d.toString()));
    adapter.sendStdin(proc, "my answer");
    expect(chunks.join("")).toBe("my answer\n");
  });

  it("sendStdin on exited process throws", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    const proc = adapter.spawn(baseOptions);
    proc.state = "exited";

    expect(() => adapter.sendStdin(proc, "answer")).toThrow("Process has exited");
  });

  it("builds correct args for new session", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn(baseOptions);

    const spawnCall = (deps.spawn as any).mock.calls[0];
    const args: string[] = spawnCall[1];
    expect(args).toContain("--output-format");
    expect(args).toContain("stream-json");
    expect(args).toContain("--session-id");
    expect(args).toContain("s1");
    expect(args).toContain("-p");
    expect(args).toContain("Fix the bug");
    expect(args).toContain("--plugin-dir");
  });

  it("builds correct args for resume session", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn({ ...baseOptions, resume: true });

    const args: string[] = (deps.spawn as any).mock.calls[0][1];
    expect(args).toContain("--continue");
    expect(args).not.toContain("--session-id");
  });

  it("uses custom CLI path when provided", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn({ ...baseOptions, claudeCliPath: "/usr/local/bin/claude" });

    expect((deps.spawn as any).mock.calls[0][0]).toBe("/usr/local/bin/claude");
  });

  it("terminate sends signal and sets state", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    const proc = adapter.spawn(baseOptions);
    adapter.terminate(proc);
    expect(proc.state).toBe("exited");
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
  });
});
