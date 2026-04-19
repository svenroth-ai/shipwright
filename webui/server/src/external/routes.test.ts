import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Hono } from "hono";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

import { SdkSessionsStore, type SdkSessionsStoreDeps } from "../core/sdk-sessions-store.js";
import { SessionWatcher } from "../core/session-watcher.js";
import { createExternalRoutes } from "./routes.js";
import { createDiagnosticsRoutes } from "../routes/diagnostics.js";

function inMemoryDeps(): SdkSessionsStoreDeps & { _files: Map<string, string> } {
  const files = new Map<string, string>();
  const existing = new Set<string>();
  return {
    _files: files,
    readFile: async (p) => {
      if (!files.has(p)) throw Object.assign(new Error("ENOENT"), { code: "ENOENT" });
      return files.get(p)!;
    },
    writeFile: async (p, data) => { files.set(p, data); existing.add(p); },
    existsSync: (p) => existing.has(p),
    mkdirSync: (p) => { existing.add(p); },
    ensureFile: (p) => { if (!files.has(p)) files.set(p, ""); existing.add(p); },
  };
}

/**
 * Integration test harness — points the SessionWatcher at a throwaway
 * "projects" directory under tmpdir so we can drop synthetic JSONLs and
 * verify the route behaves end-to-end.
 */
function mkProjectsDir(): string {
  return mkdtempSync(path.join(tmpdir(), "sdk-sessions-test-"));
}

describe("poc-external routes — integration", () => {
  let app: Hono;
  let store: SdkSessionsStore;
  let projectsDir: string;

  beforeEach(async () => {
    projectsDir = mkProjectsDir();
    const deps = inMemoryDeps();
    store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    const watcher = new SessionWatcher({ projectsDir });
    app = new Hono();
    app.route("/", createExternalRoutes({ store, watcher }));
    app.route(
      "/",
      createDiagnosticsRoutes({
        store,
        versionInfo: () => ({
          raw: "2.1.114 (Claude Code)",
          parsed: { major: 2, minor: 1, patch: 114 },
          supported: true,
        }),
      }),
    );
  });

  it("POST /tasks creates a task + GET /tasks lists it", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t1", cwd: "/tmp" }),
    });
    expect(create.status).toBe(200);
    const { task } = await create.json() as { task: { taskId: string; state: string } };
    expect(task.state).toBe("draft");
    expect(task.taskId).toBeDefined();

    const list = await app.request("/api/external/tasks");
    const json = await list.json() as { tasks: Array<{ taskId: string }> };
    expect(json.tasks.some((t) => t.taskId === task.taskId)).toBe(true);
  });

  it("POST /launch produces 3 shell forms + transitions state to awaiting_external_start", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t1", cwd: "C:/foo bar" }),
    });
    const { task } = await create.json() as { task: { taskId: string } };
    const launch = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume: false }),
    });
    expect(launch.status).toBe(200);
    const body = await launch.json() as {
      task: { state: string };
      commands: { powershell: string; cmd: string; posix: string };
    };
    expect(body.task.state).toBe("awaiting_external_start");
    expect(body.commands.powershell).toContain("--session-id");
    expect(body.commands.cmd).toContain("--session-id");
    expect(body.commands.posix).toContain("--session-id");
  });

  it("GET /transcript returns status=missing when no JSONL on disk yet", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t", cwd: "/tmp" }),
    });
    const { task } = await create.json() as { task: { taskId: string } };
    const t = await app.request(`/api/external/tasks/${task.taskId}/transcript`);
    const body = await t.json() as { status: string };
    expect(body.status).toBe("missing");
  });

  it("GET /transcript returns ok + transitions to active once JSONL exists", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t", cwd: "/tmp" }),
    });
    const { task } = await create.json() as {
      task: { taskId: string; sessionUuid: string };
    };

    // Drop a synthetic JSONL file at the expected path.
    const encodedDir = path.join(projectsDir, "encoded-fake");
    mkdirSync(encodedDir, { recursive: true });
    const content =
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: { content: "hi" },
      }) + "\n";
    writeFileSync(path.join(encodedDir, `${task.sessionUuid}.jsonl`), content, "utf-8");

    const t = await app.request(`/api/external/tasks/${task.taskId}/transcript`);
    const body = await t.json() as { status: string; task: { state: string }; chunk: { content: string } };
    expect(body.status).toBe("ok");
    expect(body.task.state).toBe("active");
    expect(body.chunk.content).toContain("hi");
  });

  it("POST /close transitions to done", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t", cwd: "/tmp" }),
    });
    const { task } = await create.json() as { task: { taskId: string } };
    const res = await app.request(`/api/external/tasks/${task.taskId}/close`, { method: "POST" });
    const body = await res.json() as { task: { state: string } };
    expect(body.task.state).toBe("done");
  });

  it("GET /diagnostics reports CLI version + launcher availability", async () => {
    const res = await app.request("/api/diagnostics");
    expect(res.status).toBe(200);
    const body = await res.json() as {
      claudeCli: { raw: string; supported: boolean };
      launchers: { copy: { available: boolean }; terminal: { available: boolean }; vscode: { available: boolean } };
    };
    expect(body.claudeCli.raw).toBe("2.1.114 (Claude Code)");
    expect(body.claudeCli.supported).toBe(true);
    expect(body.launchers.copy.available).toBe(true);
    expect(body.launchers.terminal.available).toBe(false);
    expect(body.launchers.vscode.available).toBe(false);
  });

  it("GET /inbox surfaces pending AskUserQuestion tool_use without tool_result", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t", cwd: "/tmp" }),
    });
    const { task } = await create.json() as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(projectsDir, "enc");
    mkdirSync(encodedDir, { recursive: true });
    const content =
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: {
          content: [
            { type: "text", text: "asking" },
            { type: "tool_use", id: "t1", name: "AskUserQuestion", input: { parts: [{ question: "?" }] } },
          ],
        },
      }) + "\n";
    writeFileSync(path.join(encodedDir, `${task.sessionUuid}.jsonl`), content, "utf-8");

    const res = await app.request("/api/external/inbox");
    const body = await res.json() as { items: Array<{ toolUseId: string; bestEffort: boolean }> };
    expect(body.items).toHaveLength(1);
    expect(body.items[0].toolUseId).toBe("t1");
    expect(body.items[0].bestEffort).toBe(true);
  });

  it("POST /inbox/:id/dismiss removes the entry + persists", async () => {
    // Create task + JSONL with one pending tool_use.
    const create = await app.request("/api/external/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t", cwd: "/tmp" }),
    });
    const { task } = await create.json() as { task: { taskId: string; sessionUuid: string } };
    const encodedDir = path.join(projectsDir, "enc");
    mkdirSync(encodedDir, { recursive: true });
    writeFileSync(
      path.join(encodedDir, `${task.sessionUuid}.jsonl`),
      JSON.stringify({
        type: "assistant", sessionId: task.sessionUuid,
        message: { content: [{ type: "tool_use", id: "t1", name: "AskUserQuestion", input: {} }] },
      }) + "\n",
      "utf-8",
    );
    // Prime inbox so lastProcessedByteOffset + pendingToolUseIds are written.
    await app.request("/api/external/inbox");
    // Dismiss.
    const res = await app.request("/api/external/inbox/t1/dismiss", { method: "POST" });
    expect(res.status).toBe(200);
    // Re-fetch — dismissed entries don't reappear.
    const reread = await app.request("/api/external/inbox");
    const body = await reread.json() as { items: unknown[] };
    expect(body.items).toHaveLength(0);
  });

  afterEach(() => {
    try { rmSync(projectsDir, { recursive: true, force: true }); } catch { /* ignore */ }
  });
});
