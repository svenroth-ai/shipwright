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

  it("sendUserMessage writes NDJSON user message to stdin", async () => {
    const { child, stdin } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});

    // Attach listener BEFORE spawn so we catch the initial prompt too
    const chunks: string[] = [];
    stdin.on("data", (d: Buffer) => chunks.push(d.toString()));

    const proc = adapter.spawn(baseOptions);
    proc.state = "running";
    adapter.sendUserMessage(proc, "follow-up question");

    await new Promise((r) => setTimeout(r, 20));

    const allLines = chunks.join("").split("\n").filter(Boolean);
    const parsed = allLines.map((l) => JSON.parse(l));
    const followUp = parsed.find((p) => p.message.content === "follow-up question");
    expect(followUp).toBeDefined();
    expect(followUp!.type).toBe("user");
    expect(followUp!.message.role).toBe("user");
    expect(followUp!.session_id).toBe("s1");
  });

  it("sendUserMessage supports multimodal content blocks", async () => {
    const { child, stdin } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});

    const chunks: string[] = [];
    stdin.on("data", (d: Buffer) => chunks.push(d.toString()));

    const proc = adapter.spawn(baseOptions);
    proc.state = "running";
    adapter.sendUserMessage(proc, [
      { type: "text", text: "what is this?" },
      { type: "image", source: { type: "base64", media_type: "image/png", data: "abc" } },
    ]);

    await new Promise((r) => setTimeout(r, 20));

    const allMsgs = chunks.join("").split("\n").filter(Boolean).map((s) => JSON.parse(s));
    const multimodal = allMsgs.find((m) => Array.isArray(m.message.content));
    expect(multimodal).toBeDefined();
    expect(multimodal!.message.content).toHaveLength(2);
    expect(multimodal!.message.content[0]).toEqual({ type: "text", text: "what is this?" });
    expect(multimodal!.message.content[1].type).toBe("image");
  });

  it("sendUserMessage on exited process throws", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    const proc = adapter.spawn(baseOptions);
    proc.state = "exited";

    expect(() => adapter.sendUserMessage(proc, "answer")).toThrow("Claude process has exited");
  });

  it("builds correct args for persistent NDJSON mode", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn(baseOptions);

    const spawnCall = (deps.spawn as any).mock.calls[0];
    const args: string[] = spawnCall[1];
    expect(args).toContain("--input-format");
    expect(args).toContain("--output-format");
    expect(args).toContain("stream-json");
    expect(args).toContain("--session-id");
    expect(args).toContain("s1");
    expect(args).toContain("--plugin-dir");
    expect(args).toContain("/plugins/a");
    expect(args).toContain("/plugins/b");
    // stdin must be piped now so we can send NDJSON
    expect(spawnCall[2].stdio[0]).toBe("pipe");
  });

  it("uses custom CLI path when provided", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn({ ...baseOptions, claudeCliPath: "/usr/local/bin/claude" });

    expect((deps.spawn as any).mock.calls[0][0]).toBe("/usr/local/bin/claude");
  });

  // Iterate 10 — capture real Claude session_id from system/init for --resume
  it("captures claudeSessionId from system/init NDJSON event", async () => {
    const { child, stdout } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});

    const proc = adapter.spawn(baseOptions);
    stdout.write(
      JSON.stringify({ type: "system", subtype: "init", session_id: "real-claude-sess-abc123" }) + "\n",
    );
    await new Promise((r) => setTimeout(r, 10));

    expect(proc.claudeSessionId).toBe("real-claude-sess-abc123");
  });

  it("ignores non-init system events for session capture", async () => {
    const { child, stdout } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});

    const proc = adapter.spawn(baseOptions);
    stdout.write(JSON.stringify({ type: "system", subtype: "other", session_id: "wrong" }) + "\n");
    await new Promise((r) => setTimeout(r, 10));

    expect(proc.claudeSessionId).toBeUndefined();
  });

  it("pushes --resume instead of --session-id when resumeSession is true", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn({ ...baseOptions, sessionId: "real-claude-sess-abc", resumeSession: true });

    const args: string[] = (deps.spawn as any).mock.calls[0][1];
    expect(args).toContain("--resume");
    const resumeIdx = args.indexOf("--resume");
    expect(args[resumeIdx + 1]).toBe("real-claude-sess-abc");
    expect(args).not.toContain("--session-id");
  });

  // Iterate 9 — model wire-through
  it("pushes --model <alias> when model is set", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn({ ...baseOptions, model: "sonnet" });

    const args: string[] = (deps.spawn as any).mock.calls[0][1];
    const modelIdx = args.indexOf("--model");
    expect(modelIdx).toBeGreaterThanOrEqual(0);
    expect(args[modelIdx + 1]).toBe("sonnet");
  });

  it("omits --model when model is undefined (uses CLI default)", () => {
    const { child } = createFakeChild();
    const deps = createMockDeps(child);
    const adapter = new ClaudeAdapter(deps, () => {});
    adapter.spawn(baseOptions);

    const args: string[] = (deps.spawn as any).mock.calls[0][1];
    expect(args).not.toContain("--model");
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
