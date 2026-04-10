import { describe, it, expect, vi } from "vitest";
import { ProcessGovernor } from "./process-governor.js";
import type { GovernorDeps } from "./process-governor.js";
import type { ClaudeAdapter, ClaudeProcess, ClaudeSpawnOptions } from "./claude-adapter.js";

function mockDeps(): GovernorDeps {
  return {
    isProcessRunning: vi.fn(() => false),
    kill: vi.fn(),
    readFile: vi.fn(async () => "[]"),
    writeFile: vi.fn(async () => {}),
    existsSync: vi.fn(() => true),
    mkdirSync: vi.fn(),
  };
}

let pidCounter = 1000;
function mockAdapter(): ClaudeAdapter {
  return {
    spawn: vi.fn((opts: ClaudeSpawnOptions) => ({
      pid: pidCounter++,
      taskId: opts.taskId,
      projectId: opts.projectId,
      sessionId: opts.sessionId ?? opts.taskId,
      state: "running",
      process: {} as any,
    })),
  } as unknown as ClaudeAdapter;
}

function makeOptions(taskId: string): ClaudeSpawnOptions {
  return {
    projectDir: "/tmp",
    projectId: "p1",
    taskId,
    resume: false,
    pluginDirs: [],
    prompt: "test",
  };
}

describe("ProcessGovernor", () => {
  it("spawns processes up to maxConcurrent", async () => {
    const deps = mockDeps();
    const adapter = mockAdapter();
    const gov = new ProcessGovernor(3, adapter, deps, "/tmp/pids.json");

    const r1 = await gov.acquire(makeOptions("t1"));
    const r2 = await gov.acquire(makeOptions("t2"));
    const r3 = await gov.acquire(makeOptions("t3"));
    expect(r1).not.toBe("queued");
    expect(r2).not.toBe("queued");
    expect(r3).not.toBe("queued");
    expect(gov.getAllActive()).toHaveLength(3);
  });

  it("queues 4th process when at capacity", async () => {
    const deps = mockDeps();
    const adapter = mockAdapter();
    const gov = new ProcessGovernor(3, adapter, deps, "/tmp/pids.json");

    await gov.acquire(makeOptions("t1"));
    await gov.acquire(makeOptions("t2"));
    await gov.acquire(makeOptions("t3"));
    const r4 = await gov.acquire(makeOptions("t4"));
    expect(r4).toBe("queued");
    expect(gov.getQueueLength()).toBe(1);
  });

  it("drains queue on release", async () => {
    const deps = mockDeps();
    const adapter = mockAdapter();
    const gov = new ProcessGovernor(2, adapter, deps, "/tmp/pids.json");

    await gov.acquire(makeOptions("t1"));
    await gov.acquire(makeOptions("t2"));
    await gov.acquire(makeOptions("t3")); // queued

    await gov.release("t1");
    expect(gov.getQueueLength()).toBe(0);
    expect(gov.getAllActive()).toHaveLength(2);
  });

  it("cleanupOrphans kills running orphans and removes stale", async () => {
    const deps = mockDeps();
    (deps.readFile as any).mockResolvedValue(
      JSON.stringify([
        { pid: 111, taskId: "orphan1" },
        { pid: 222, taskId: "stale1" },
      ])
    );
    (deps.isProcessRunning as any).mockImplementation((pid: number) => pid === 111);

    const adapter = mockAdapter();
    const gov = new ProcessGovernor(3, adapter, deps, "/tmp/pids.json");
    const result = await gov.cleanupOrphans();
    expect(result.killed).toBe(1);
    expect(result.stale).toBe(1);
    expect(deps.kill).toHaveBeenCalledWith(111);
  });

  it("persistPids writes correct JSON", async () => {
    const deps = mockDeps();
    const adapter = mockAdapter();
    const gov = new ProcessGovernor(3, adapter, deps, "/tmp/pids.json");
    await gov.acquire(makeOptions("t1"));
    const writeCall = (deps.writeFile as any).mock.calls[0];
    const written = JSON.parse(writeCall[1]);
    expect(written).toHaveLength(1);
    expect(written[0].taskId).toBe("t1");
  });

  it("getProcess returns correct process", async () => {
    const deps = mockDeps();
    const adapter = mockAdapter();
    const gov = new ProcessGovernor(3, adapter, deps, "/tmp/pids.json");
    await gov.acquire(makeOptions("t1"));
    expect(gov.getProcess("t1")).toBeDefined();
    expect(gov.getProcess("t99")).toBeUndefined();
  });
});
