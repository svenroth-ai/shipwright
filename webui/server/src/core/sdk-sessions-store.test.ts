import { describe, it, expect, beforeEach } from "vitest";

import { SdkSessionsStore, type SdkSessionsStoreDeps } from "./sdk-sessions-store.js";

function inMemoryDeps(initial?: Record<string, string>): SdkSessionsStoreDeps & {
  __files: Map<string, string>;
  __existing: Set<string>;
} {
  const files = new Map<string, string>();
  if (initial) for (const [p, c] of Object.entries(initial)) files.set(p, c);
  const existing = new Set<string>(files.keys());
  return {
    __files: files,
    __existing: existing,
    readFile: async (p) => {
      if (!files.has(p)) throw Object.assign(new Error("ENOENT"), { code: "ENOENT" });
      return files.get(p)!;
    },
    writeFile: async (p, data) => {
      files.set(p, data);
      existing.add(p);
    },
    existsSync: (p) => existing.has(p),
    mkdirSync: (p) => { existing.add(p); },
    ensureFile: (p) => {
      if (!files.has(p)) files.set(p, "");
      existing.add(p);
    },
  };
}

describe("SdkSessionsStore — create/list/patch/delete", () => {
  it("creates a task in draft state with a fresh UUID", async () => {
    const deps = inMemoryDeps();
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    const task = store.create({ title: "t", cwd: "/tmp" });
    expect(task.state).toBe("draft");
    expect(task.title).toBe("t");
    expect(task.cwd).toBe("/tmp");
    expect(task.sessionUuid).toMatch(/^[0-9a-f-]{36}$/);
    expect(task.taskId).toMatch(/^[0-9a-f-]{36}$/);
    expect(task.inbox).toEqual({
      pendingToolUseIds: [],
      dismissedToolUseIds: [],
      lastProcessedByteOffset: 0,
    });
  });

  it("list returns tasks newest-first", async () => {
    const deps = inMemoryDeps();
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    const a = store.create({ title: "a", cwd: "/tmp" });
    await new Promise((r) => setTimeout(r, 2));
    const b = store.create({ title: "b", cwd: "/tmp" });
    const list = store.list();
    expect(list[0].taskId).toBe(b.taskId);
    expect(list[1].taskId).toBe(a.taskId);
  });

  it("patch updates only the given fields", async () => {
    const deps = inMemoryDeps();
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    const task = store.create({ title: "t", cwd: "/tmp" });
    store.patch(task.taskId, { state: "active", lastJsonlSeenMtimeMs: 1234 });
    const got = store.get(task.taskId);
    expect(got?.state).toBe("active");
    expect(got?.lastJsonlSeenMtimeMs).toBe(1234);
    expect(got?.title).toBe("t");
  });

  it("delete removes the task", async () => {
    const deps = inMemoryDeps();
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    const task = store.create({ title: "t", cwd: "/tmp" });
    expect(store.delete(task.taskId)).toBe(true);
    expect(store.get(task.taskId)).toBeUndefined();
  });
});

describe("SdkSessionsStore — persist/load round-trip", () => {
  it("persists state and loads it back intact", async () => {
    const deps = inMemoryDeps();
    const path = "/store/sdk-sessions.json";
    const a = new SdkSessionsStore(path, deps);
    await a.load();
    const task = a.create({ title: "t", cwd: "/tmp", pluginDirs: ["/p1"] });
    a.patch(task.taskId, { state: "active" });
    await a.persist();

    // Fresh store instance with same deps reads back.
    const b = new SdkSessionsStore(path, deps);
    await b.load();
    const loaded = b.get(task.taskId);
    expect(loaded?.title).toBe("t");
    expect(loaded?.state).toBe("active");
    expect(loaded?.pluginDirs).toEqual(["/p1"]);
  });
});

describe("SdkSessionsStore — concurrent rename with proper-lockfile", () => {
  /**
   * Two writers race to rename the same task. With a serializing lock we
   * expect both writes to succeed (one waits for the other) and the
   * persisted file to contain one of the two titles — never a corrupted
   * mid-state. We use a real temp file + the real proper-lockfile so the
   * lock semantics aren't bypassed by the in-memory fake.
   */
  it("real proper-lockfile serializes two parallel rename+persist calls", async () => {
    const fs = await import("node:fs");
    const fsp = await import("node:fs/promises");
    const path = await import("node:path");
    const os = await import("node:os");
    const lockfile = await import("proper-lockfile");

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "sdk-sessions-lock-"));
    const file = path.join(dir, "sdk-sessions.json");

    const realDeps = {
      readFile: (p: string, e: string) => fsp.readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => fsp.writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => { fs.mkdirSync(p, o); },
      lock: async (p: string) => lockfile.lock(p, { retries: { retries: 5, minTimeout: 20 } }),
      ensureFile: (p: string) => { if (!fs.existsSync(p)) fs.writeFileSync(p, ""); },
    };

    const seed = new SdkSessionsStore(file, realDeps);
    await seed.load();
    const t = seed.create({ title: "init", cwd: "/tmp" });
    await seed.persist();

    // Two independent store instances racing to rename the same task.
    const a = new SdkSessionsStore(file, realDeps);
    const b = new SdkSessionsStore(file, realDeps);
    await a.load();
    await b.load();
    a.patch(t.taskId, { title: "from-a" });
    b.patch(t.taskId, { title: "from-b" });
    await Promise.all([a.persist(), b.persist()]);

    const final = new SdkSessionsStore(file, realDeps);
    await final.load();
    const got = final.get(t.taskId);
    expect(got).toBeDefined();
    expect(["from-a", "from-b"]).toContain(got!.title);

    // Cleanup.
    try { fs.rmSync(dir, { recursive: true, force: true }); } catch { /* ignore */ }
  }, 20_000);
});

describe("SdkSessionsStore — corruption tolerance", () => {
  it("starts empty when the file is malformed JSON (does not throw)", async () => {
    const deps = inMemoryDeps({ "/store/sdk-sessions.json": "this is not json" });
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    expect(store.list()).toEqual([]);
  });

  it("drops rows that fail schema validation but keeps the rest", async () => {
    const payload = JSON.stringify({
      schemaVersion: 1,
      sessions: {
        good: {
          taskId: "good",
          sessionUuid: "u",
          cwd: "/tmp",
          pluginDirs: [],
          state: "draft",
          title: "good",
          createdAt: "now",
          inbox: { pendingToolUseIds: [], dismissedToolUseIds: [], lastProcessedByteOffset: 0 },
        },
        bad: { nope: "invalid" },
      },
    });
    const deps = inMemoryDeps({ "/store/sdk-sessions.json": payload });
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    const list = store.list();
    expect(list).toHaveLength(1);
    expect(list[0].taskId).toBe("good");
  });

  it("starts empty on schemaVersion mismatch (future-proof)", async () => {
    const payload = JSON.stringify({ schemaVersion: 99, sessions: {} });
    const deps = inMemoryDeps({ "/store/sdk-sessions.json": payload });
    const store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    expect(store.list()).toEqual([]);
  });
});
