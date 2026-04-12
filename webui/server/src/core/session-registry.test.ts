import { describe, it, expect, vi } from "vitest";
import { SessionRegistry } from "./session-registry.js";

function mockDeps() {
  const storage: Record<string, string> = {};
  return {
    storage,
    readFile: vi.fn(async (path: string) => storage[path] ?? ""),
    writeFile: vi.fn(async (path: string, data: string) => {
      storage[path] = data;
    }),
    existsSync: vi.fn((path: string) => path in storage),
    mkdirSync: vi.fn(),
  };
}

describe("SessionRegistry", () => {
  it("set stores mapping and persists to disk", async () => {
    const deps = mockDeps();
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    await reg.set("task-1", "claude-session-abc");
    expect(reg.get("task-1")).toBe("claude-session-abc");
    expect(deps.writeFile).toHaveBeenCalled();
  });

  it("get returns undefined for unknown task", async () => {
    const deps = mockDeps();
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    expect(reg.get("nope")).toBeUndefined();
  });

  it("load restores mappings from disk", async () => {
    const deps = mockDeps();
    deps.storage["/tmp/sessions.json"] = JSON.stringify({ "t1": "sess-1", "t2": "sess-2" });
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    await reg.load();
    expect(reg.get("t1")).toBe("sess-1");
    expect(reg.get("t2")).toBe("sess-2");
  });

  it("load is idempotent", async () => {
    const deps = mockDeps();
    deps.storage["/tmp/sessions.json"] = JSON.stringify({ "t1": "sess-1" });
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    await reg.load();
    await reg.load();
    expect(deps.readFile).toHaveBeenCalledTimes(1);
  });

  it("set skips write if value unchanged", async () => {
    const deps = mockDeps();
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    await reg.set("t1", "sess-1");
    deps.writeFile.mockClear();
    await reg.set("t1", "sess-1"); // same value
    expect(deps.writeFile).not.toHaveBeenCalled();
  });

  it("load handles missing file gracefully", async () => {
    const deps = mockDeps();
    const reg = new SessionRegistry(deps, "/tmp/nonexistent.json");
    await reg.load();
    expect(reg.get("anything")).toBeUndefined();
  });

  it("load handles corrupt JSON gracefully", async () => {
    const deps = mockDeps();
    deps.storage["/tmp/sessions.json"] = "{ not valid json";
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    await reg.load();
    expect(reg.get("t1")).toBeUndefined();
  });

  it("set ignores empty taskId or sessionId", async () => {
    const deps = mockDeps();
    const reg = new SessionRegistry(deps, "/tmp/sessions.json");
    await reg.set("", "sess");
    await reg.set("t1", "");
    expect(deps.writeFile).not.toHaveBeenCalled();
  });
});
