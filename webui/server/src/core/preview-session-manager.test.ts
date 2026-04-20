import { describe, it, expect, beforeEach, vi } from "vitest";
import { EventEmitter } from "node:events";

import {
  PreviewSessionManager,
  PreviewExitedEarlyError,
  PreviewPortInUseError,
  PreviewProfileInvalidError,
  PreviewSpawnFailedError,
  PreviewTimeoutError,
} from "./preview-session-manager.js";

// A ChildProcess stub that exposes just the bits our manager touches.
function fakeChild(): {
  emit: EventEmitter["emit"];
  on: EventEmitter["on"];
  once: EventEmitter["once"];
  removeListener: EventEmitter["removeListener"];
  kill: ReturnType<typeof vi.fn>;
  stdin: null;
  stdout: null;
  stderr: null;
  pid: number;
  exitCode: number | null;
  killed: boolean;
} {
  const ev = new EventEmitter();
  // Boxed state so the manager can observe "has the child died?".
  const state = { exitCode: null as number | null, killed: false };
  const child = {
    emit: ev.emit.bind(ev),
    on: ev.on.bind(ev),
    once: ev.once.bind(ev),
    removeListener: ev.removeListener.bind(ev),
    kill: vi.fn((_sig?: NodeJS.Signals | number) => {
      state.killed = true;
      // Simulate the child actually exiting async so the late-bound
      // `exit` listener fires in tests that need cleanup.
      setImmediate(() => ev.emit("exit", 143));
      return true;
    }),
    stdin: null,
    stdout: null,
    stderr: null,
    pid: 12345,
    get exitCode() {
      return state.exitCode;
    },
    get killed() {
      return state.killed;
    },
  };
  return child as unknown as ReturnType<typeof fakeChild>;
}

describe("PreviewSessionManager.tokenizeCommand", () => {
  it("tokenizes 'npm run dev' into ['npm', 'run', 'dev']", () => {
    expect(PreviewSessionManager.tokenizeCommand("npm run dev")).toEqual([
      "npm",
      "run",
      "dev",
    ]);
  });

  it("rejects commands containing && / | / ; (shell operators)", () => {
    expect(() =>
      PreviewSessionManager.tokenizeCommand("npm run dev && echo done"),
    ).toThrow(PreviewProfileInvalidError);
    expect(() =>
      PreviewSessionManager.tokenizeCommand("npm run dev | tee log"),
    ).toThrow(PreviewProfileInvalidError);
    expect(() =>
      PreviewSessionManager.tokenizeCommand("npm run dev ; true"),
    ).toThrow(PreviewProfileInvalidError);
  });

  it("honors quotes so `foo \"bar baz\"` yields ['foo','bar baz']", () => {
    expect(PreviewSessionManager.tokenizeCommand('foo "bar baz"')).toEqual([
      "foo",
      "bar baz",
    ]);
  });

  it("rejects empty / whitespace commands", () => {
    expect(() => PreviewSessionManager.tokenizeCommand("")).toThrow(
      PreviewProfileInvalidError,
    );
    expect(() => PreviewSessionManager.tokenizeCommand("   ")).toThrow(
      PreviewProfileInvalidError,
    );
    expect(() => PreviewSessionManager.tokenizeCommand(undefined)).toThrow(
      PreviewProfileInvalidError,
    );
  });
});

describe("PreviewSessionManager.spawn", () => {
  let mgr: PreviewSessionManager;

  beforeEach(() => {
    mgr = new PreviewSessionManager();
  });

  function baseProfile() {
    return {
      dev_server: {
        command: "npm run dev",
        port: 5173,
        ready_path: "/",
        ready_timeout_seconds: 5,
      },
    };
  }

  it("spawns with shell:false + pre-tokenized argv, resolves to {url, sessionId} after readiness", async () => {
    const spawn = vi.fn(() => fakeChild() as unknown);
    const probePort = vi.fn(async () => true);
    const probeReady = vi.fn(async () => true);

    const entry = await mgr.spawn("p1", baseProfile(), {
      cwd: "/tmp",
      spawn: spawn as unknown as never,
      probePort,
      probeReady,
      env: {},
    });

    expect(spawn).toHaveBeenCalledTimes(1);
    const call = spawn.mock.calls[0] as unknown as [
      string,
      string[],
      { shell: boolean; cwd: string },
    ];
    expect(call[0]).toBe("npm");
    expect(call[1]).toEqual(["run", "dev"]);
    expect(call[2].shell).toBe(false);
    expect(call[2].cwd).toBe("/tmp");

    expect(entry.url).toBe("http://localhost:5173");
    expect(entry.sessionId).toMatch(/^[0-9a-f-]{36}$/);
    expect(entry.profileHash).toMatch(/^[a-f0-9]{12}$/);
  });

  it("returns cached entry on second call (idempotent, no re-spawn)", async () => {
    const spawn = vi.fn(() => fakeChild() as unknown);
    const probePort = vi.fn(async () => true);
    const probeReady = vi.fn(async () => true);

    const a = await mgr.spawn("p1", baseProfile(), {
      cwd: "/tmp",
      spawn: spawn as unknown as never,
      probePort,
      probeReady,
      env: {},
    });
    const b = await mgr.spawn("p1", baseProfile(), {
      cwd: "/tmp",
      spawn: spawn as unknown as never,
      probePort,
      probeReady,
      env: {},
    });

    expect(spawn).toHaveBeenCalledTimes(1);
    expect(b.sessionId).toBe(a.sessionId);
    expect(b.url).toBe(a.url);
  });

  it("re-spawns after the child exits (purges cache)", async () => {
    const spawn = vi.fn(() => fakeChild() as unknown);
    const probePort = vi.fn(async () => true);
    const probeReady = vi.fn(async () => true);

    const a = await mgr.spawn("p1", baseProfile(), {
      cwd: "/tmp",
      spawn: spawn as unknown as never,
      probePort,
      probeReady,
      env: {},
    });

    // Kill it — auto-purge runs via the exit listener we attached.
    a.child.kill("SIGTERM");
    await new Promise((r) => setImmediate(r));

    expect(mgr.get("p1")).toBeUndefined();

    const b = await mgr.spawn("p1", baseProfile(), {
      cwd: "/tmp",
      spawn: spawn as unknown as never,
      probePort,
      probeReady,
      env: {},
    });

    expect(spawn).toHaveBeenCalledTimes(2);
    expect(b.sessionId).not.toBe(a.sessionId);
  });

  it("throws PreviewProfileInvalidError on a pipeline command (no spawn attempt)", async () => {
    const spawn = vi.fn();
    await expect(
      mgr.spawn(
        "p1",
        {
          dev_server: {
            command: "npm run dev && echo done",
            port: 5173,
            ready_timeout_seconds: 1,
          },
        },
        {
          cwd: "/tmp",
          spawn: spawn as unknown as never,
          probePort: async () => true,
          probeReady: async () => true,
          env: {},
        },
      ),
    ).rejects.toBeInstanceOf(PreviewProfileInvalidError);
    expect(spawn).not.toHaveBeenCalled();
  });

  it("throws PreviewSpawnFailedError when spawn throws ENOENT", async () => {
    const spawn = vi.fn(() => {
      const err = new Error("spawn ENOENT") as NodeJS.ErrnoException;
      err.code = "ENOENT";
      throw err;
    });
    await expect(
      mgr.spawn("p1", baseProfile(), {
        cwd: "/tmp",
        spawn: spawn as unknown as never,
        probePort: async () => true,
        probeReady: async () => true,
        env: {},
      }),
    ).rejects.toBeInstanceOf(PreviewSpawnFailedError);
  });

  it("throws PreviewPortInUseError when the port probe reports not free", async () => {
    const spawn = vi.fn(() => fakeChild() as unknown);
    await expect(
      mgr.spawn("p1", baseProfile(), {
        cwd: "/tmp",
        spawn: spawn as unknown as never,
        probePort: async () => false,
        probeReady: async () => true,
        env: {},
      }),
    ).rejects.toBeInstanceOf(PreviewPortInUseError);
    expect(spawn).not.toHaveBeenCalled();
  });

  it("throws PreviewExitedEarlyError when the child exits before readiness", async () => {
    const child = fakeChild();
    const spawn = vi.fn(() => child as unknown);
    // Readiness never returns true — we'll pre-empt it via an exit event.
    const neverReady = vi.fn(async () => false);

    const p = mgr.spawn("p1", baseProfile(), {
      cwd: "/tmp",
      spawn: spawn as unknown as never,
      probePort: async () => true,
      probeReady: neverReady,
      env: {},
    });

    // Tick so the manager attaches its `exit` listener.
    await new Promise((r) => setImmediate(r));
    child.emit("exit", 1);

    await expect(p).rejects.toBeInstanceOf(PreviewExitedEarlyError);
    expect(mgr.size()).toBe(0);
  });

  it("throws PreviewTimeoutError when readiness never succeeds within the timeout", async () => {
    const spawn = vi.fn(() => fakeChild() as unknown);
    const probeReady = vi.fn(async () => false);

    // Mock the clock to blow past the 1s timeout immediately.
    let t = 0;
    const now = () => {
      t += 10_000; // jump 10s per call → exceeds 1s timeout on the first iteration
      return t;
    };

    await expect(
      mgr.spawn(
        "p1",
        {
          dev_server: {
            command: "npm run dev",
            port: 5173,
            ready_path: "/",
            ready_timeout_seconds: 1,
          },
        },
        {
          cwd: "/tmp",
          spawn: spawn as unknown as never,
          probePort: async () => true,
          probeReady,
          now,
          env: {},
        },
      ),
    ).rejects.toBeInstanceOf(PreviewTimeoutError);
  });
});

describe("PreviewSessionManager.killAll", () => {
  it("SIGTERMs every tracked child + clears the map", async () => {
    const mgr = new PreviewSessionManager();
    const child = fakeChild();
    const spawn = vi.fn(() => child as unknown);

    await mgr.spawn(
      "p1",
      {
        dev_server: {
          command: "npm run dev",
          port: 5173,
          ready_timeout_seconds: 5,
        },
      },
      {
        cwd: "/tmp",
        spawn: spawn as unknown as never,
        probePort: async () => true,
        probeReady: async () => true,
        env: {},
      },
    );

    expect(mgr.size()).toBe(1);
    mgr.killAll();
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");
    expect(mgr.size()).toBe(0);
  });
});
