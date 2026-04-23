/*
 * Iterate 3 section 03 — route-layer tests for the new
 *  - GET /api/external/projects/:projectId/actions
 *  - POST /api/external/projects/:projectId/preview
 *  - POST /api/projects/:id/actions-stub
 *  - POST /api/external/tasks/:id/launch (extended body validation)
 * endpoints on top of the existing /tasks harness.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { Hono } from "hono";
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

import {
  SdkSessionsStore,
  type SdkSessionsStoreDeps,
} from "../core/sdk-sessions-store.js";
import { SessionWatcher } from "../core/session-watcher.js";
import {
  createExternalRoutes,
  type ExternalRouteProjectView,
} from "./routes.js";
import { clearActionsCache } from "../core/project-actions-loader.js";
import {
  PreviewSessionManager,
} from "../core/preview-session-manager.js";
import { EventEmitter } from "node:events";

function inMemoryStoreDeps(): SdkSessionsStoreDeps & {
  _files: Map<string, string>;
} {
  const files = new Map<string, string>();
  const existing = new Set<string>();
  return {
    _files: files,
    readFile: async (p) => {
      if (!files.has(p)) throw Object.assign(new Error("ENOENT"), { code: "ENOENT" });
      return files.get(p)!;
    },
    writeFile: async (p, data) => {
      files.set(p, data);
      existing.add(p);
    },
    existsSync: (p) => existing.has(p),
    mkdirSync: (p) => {
      existing.add(p);
    },
    ensureFile: (p) => {
      if (!files.has(p)) files.set(p, "");
      existing.add(p);
    },
  };
}

function fakeChild(): unknown {
  const ev = new EventEmitter();
  const state = { exitCode: null as number | null, killed: false };
  return {
    emit: ev.emit.bind(ev),
    on: ev.on.bind(ev),
    once: ev.once.bind(ev),
    removeListener: ev.removeListener.bind(ev),
    kill: vi.fn(() => {
      state.killed = true;
      setImmediate(() => ev.emit("exit", 143));
      return true;
    }),
    stdin: null,
    stdout: null,
    stderr: null,
    pid: 99999,
    get exitCode() {
      return state.exitCode;
    },
    get killed() {
      return state.killed;
    },
  };
}

describe("actions/preview/stub routes", () => {
  let app: Hono;
  let store: SdkSessionsStore;
  let previewMgr: PreviewSessionManager;
  let projectPath: string;
  const PROJECT_ID = "project-001";

  function defaultProject(): ExternalRouteProjectView {
    return {
      id: PROJECT_ID,
      name: "demo",
      path: projectPath,
      profile: "supabase-nextjs",
    };
  }

  function fakeProfile() {
    // Mimics supabase-nextjs.json minus the huge payload.
    return {
      name: "supabase-nextjs",
      stack: { frontend: { next: "^16.2.0" } },
      dev_server: {
        command: "npm run dev",
        port: 3000,
        ready_path: "/",
        ready_timeout_seconds: 60,
      },
    };
  }

  beforeEach(async () => {
    clearActionsCache();
    projectPath = mkdtempSync(path.join(tmpdir(), "actions-route-test-"));
    const deps = inMemoryStoreDeps();
    store = new SdkSessionsStore("/store/sdk-sessions.json", deps);
    await store.load();
    previewMgr = new PreviewSessionManager();
    const watcher = new SessionWatcher({ projectsDir: projectPath });
    app = new Hono();
    app.route(
      "/",
      createExternalRoutes({
        store,
        watcher,
        getProjectById: (id) =>
          id === PROJECT_ID ? defaultProject() : undefined,
        getKnownProjectIds: () => new Set([PROJECT_ID]),
        previewManager: previewMgr,
        loadProfile: () => fakeProfile(),
      }),
    );
  });

  afterEach(() => {
    previewMgr.killAll();
    rmSync(projectPath, { recursive: true, force: true });
  });

  // ---- GET /actions ----

  it("GET /projects/:id/actions returns bundled default shape when no .webui/actions.json", async () => {
    const r = await app.request(
      `/api/external/projects/${PROJECT_ID}/actions`,
    );
    expect(r.status).toBe(200);
    const body = (await r.json()) as {
      actions: Array<{ id: string }>;
      phases: Array<{ id: string }>;
      defaults: { autonomy: string };
      preview: { enabled: boolean; command: string | null };
      diagnostics: unknown[];
    };
    expect(body.actions.map((a) => a.id)).toEqual([
      "new-task",
      "new-pipeline",
      "new-iterate",
    ]);
    // 2026-04-23 — `adopt` phase added to default-actions.json.
    expect(body.phases.length).toBe(10);
    expect(body.phases.some((p: { id: string }) => p.id === "adopt")).toBe(true);
    expect(body.defaults.autonomy).toBe("guided");
    expect(body.preview.enabled).toBe(true);
    expect(body.preview.command).toBe("npm run dev");
    expect(body.diagnostics).toEqual([]);
  });

  it("GET /projects/:id/actions reports diagnostic when .webui/actions.json is malformed", async () => {
    const webuiDir = path.join(projectPath, ".webui");
    mkdirSync(webuiDir, { recursive: true });
    writeFileSync(path.join(webuiDir, "actions.json"), "{ not json", "utf-8");

    const r = await app.request(
      `/api/external/projects/${PROJECT_ID}/actions`,
    );
    expect(r.status).toBe(200);
    const body = (await r.json()) as {
      diagnostics: Array<{ code: string }>;
    };
    expect(body.diagnostics.length).toBe(1);
    expect(body.diagnostics[0].code).toBe("actions_file_malformed");
  });

  it("GET /projects/:id/actions returns 404 for unknown project", async () => {
    const r = await app.request(`/api/external/projects/ghost/actions`);
    expect(r.status).toBe(404);
    const body = (await r.json()) as { error: string };
    expect(body.error).toBe("project_not_found");
  });

  it("GET /projects/:id/actions rejects template with unknown placeholder (invalid_placeholder 400)", async () => {
    const webuiDir = path.join(projectPath, ".webui");
    mkdirSync(webuiDir, { recursive: true });
    writeFileSync(
      path.join(webuiDir, "actions.json"),
      JSON.stringify({
        schemaVersion: 1,
        defaults: { autonomy: "guided" },
        actions: [
          {
            id: "new-task",
            label: "New task",
            kind: "external_launch",
            command_template: "claude /shipwright-{task.priority}",
          },
        ],
        phases: [{ id: "build", label: "Build" }],
        preview: { enabled: "auto" },
      }),
      "utf-8",
    );
    const r = await app.request(
      `/api/external/projects/${PROJECT_ID}/actions`,
    );
    expect(r.status).toBe(400);
    const body = (await r.json()) as { error: string; placeholder: string; actionId: string };
    expect(body.error).toBe("invalid_placeholder");
    expect(body.placeholder).toBe("task.priority");
    expect(body.actionId).toBe("new-task");
  });

  it("GET /projects/:id/actions resolves preview.enabled per § 2.1 precedence — actions:false forces off", async () => {
    const webuiDir = path.join(projectPath, ".webui");
    mkdirSync(webuiDir, { recursive: true });
    writeFileSync(
      path.join(webuiDir, "actions.json"),
      JSON.stringify({
        schemaVersion: 1,
        defaults: { autonomy: "guided" },
        actions: [
          {
            id: "new-task",
            label: "New task",
            kind: "external_launch",
            command_template: "claude",
          },
        ],
        phases: [{ id: "build", label: "Build" }],
        preview: { enabled: false },
      }),
      "utf-8",
    );
    const r = await app.request(
      `/api/external/projects/${PROJECT_ID}/actions`,
    );
    const body = (await r.json()) as { preview: { enabled: boolean } };
    expect(body.preview.enabled).toBe(false);
  });

  // ---- POST /preview ----

  it("POST /projects/:id/preview returns {url, sessionId} on happy path", async () => {
    // Swap the manager for one that mocks spawn.
    const mgr = new PreviewSessionManager();
    const fakeApp = new Hono();
    fakeApp.route(
      "/",
      createExternalRoutes({
        store,
        watcher: new SessionWatcher({ projectsDir: projectPath }),
        getProjectById: (id) => (id === PROJECT_ID ? defaultProject() : undefined),
        previewManager: mgr,
        loadProfile: () => fakeProfile(),
      }),
    );

    // Pre-seed via direct manager call — the route's actual spawn path uses
    // real node fs/net. Simulate by calling the manager directly first to
    // cache an entry, then hit the route: should return cached.
    await mgr.spawn(PROJECT_ID, fakeProfile(), {
      cwd: projectPath,
      spawn: (() => fakeChild()) as unknown as never,
      probePort: async () => true,
      probeReady: async () => true,
      env: {},
    });

    const r = await fakeApp.request(
      `/api/external/projects/${PROJECT_ID}/preview`,
      { method: "POST" },
    );
    expect(r.status).toBe(200);
    const body = (await r.json()) as { url: string; sessionId: string };
    expect(body.url).toBe("http://localhost:3000");
    expect(body.sessionId).toMatch(/^[0-9a-f-]{36}$/);

    mgr.killAll();
  });

  it("POST /projects/:id/preview returns 400 preview_profile_invalid when profile missing", async () => {
    const fakeApp = new Hono();
    fakeApp.route(
      "/",
      createExternalRoutes({
        store,
        watcher: new SessionWatcher({ projectsDir: projectPath }),
        getProjectById: (id) =>
          id === PROJECT_ID
            ? { id: PROJECT_ID, name: "demo", path: projectPath, profile: "unknown" }
            : undefined,
        previewManager: previewMgr,
        loadProfile: () => null,
      }),
    );
    const r = await fakeApp.request(
      `/api/external/projects/${PROJECT_ID}/preview`,
      { method: "POST" },
    );
    expect(r.status).toBe(400);
    const body = (await r.json()) as { error: string };
    expect(body.error).toBe("preview_profile_invalid");
  });

  // ---- POST /actions-stub ----

  it("POST /projects/:id/actions-stub creates .webui/actions.json + is idempotent", async () => {
    const r1 = await app.request(
      `/api/projects/${PROJECT_ID}/actions-stub`,
      { method: "POST" },
    );
    expect(r1.status).toBe(200);
    const file = path.join(projectPath, ".webui", "actions.json");
    expect(existsSync(file)).toBe(true);
    const content = readFileSync(file, "utf-8");
    expect(content).toContain("schemaVersion");

    // Second call is a no-op — does not overwrite.
    const tampered = content.replace(
      "schemaVersion",
      "schemaVersion_user_added",
    );
    writeFileSync(file, tampered, "utf-8");
    const r2 = await app.request(
      `/api/projects/${PROJECT_ID}/actions-stub`,
      { method: "POST" },
    );
    expect(r2.status).toBe(200);
    const after = readFileSync(file, "utf-8");
    expect(after).toBe(tampered);
  });

  it("POST /projects/:id/actions-stub returns 404 for unknown project", async () => {
    const r = await app.request(`/api/projects/ghost/actions-stub`, {
      method: "POST",
    });
    expect(r.status).toBe(404);
  });

  // ---- POST /tasks/:id/launch (extended) ----

  it("POST /tasks/:id/launch accepts {description, autonomy} body + preserves shell-form shape", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t1", cwd: "C:/tmp" }),
    });
    const { task } = (await create.json()) as { task: { taskId: string } };
    const r = await app.request(
      `/api/external/tasks/${task.taskId}/launch`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: "write tests",
          autonomy: "autonomous",
        }),
      },
    );
    expect(r.status).toBe(200);
    const body = (await r.json()) as {
      task: { state: string };
      commands: { powershell: string; cmd: string; posix: string };
    };
    expect(body.task.state).toBe("awaiting_external_start");
    expect(body.commands.powershell).toContain("--session-id");
  });

  it("POST /tasks/:id/launch returns 409 launch_invalid_state on done task", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t1", cwd: "C:/tmp" }),
    });
    const { task } = (await create.json()) as { task: { taskId: string } };
    await app.request(`/api/external/tasks/${task.taskId}/close`, {
      method: "POST",
    });
    const r = await app.request(
      `/api/external/tasks/${task.taskId}/launch`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    expect(r.status).toBe(409);
    const body = (await r.json()) as { error: string; state: string };
    expect(body.error).toBe("launch_invalid_state");
    expect(body.state).toBe("done");
  });

  it("POST /tasks/:id/launch from draft state is allowed (backlog → in-progress)", async () => {
    const create = await app.request("/api/external/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "t1", cwd: "C:/tmp" }),
    });
    const { task } = (await create.json()) as { task: { taskId: string; state: string } };
    expect(task.state).toBe("draft");
    const r = await app.request(
      `/api/external/tasks/${task.taskId}/launch`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    expect(r.status).toBe(200);
  });

  // ── 2026-04-23 — iterate-20260423-launch-command-wiring ──
  //
  // The launch route must build the COMPLETE shipwright-slash command
  // via substitutePlaceholders when the NewIssueModal hands in an
  // actionId + phase, not the legacy --session-id/--name stub.
  describe("launch command passthrough (2026-04-23)", () => {
    async function createTask(title = "t1", cwd = "C:/tmp", projectId = PROJECT_ID) {
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, cwd, projectId }),
      });
      return (await r.json()) as { task: { taskId: string } };
    }

    it("substitutes {task.phase} into the slash command when actionId+phase present", async () => {
      const { task } = await createTask("Testing the test phase");
      const r = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actionId: "new-task",
          phase: "test",
          phaseLabel: "Test",
          description: "run vitest suite",
          autonomy: "autonomous",
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as {
        commands: { powershell: string; cmd: string; posix: string };
      };
      // Slash command routed correctly — proves {task.phase} substituted.
      expect(body.commands.posix).toContain("/shipwright-test");
      expect(body.commands.powershell).toContain("/shipwright-test");
      expect(body.commands.cmd).toContain("/shipwright-test");
      // Must NOT contain the default/build fallback.
      expect(body.commands.posix).not.toContain("/shipwright-build");
    });

    it("substitutes {task.description?} into the command when provided", async () => {
      const { task } = await createTask();
      const r = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actionId: "new-task",
          phase: "build",
          phaseLabel: "Build",
          description: "fix-the-login-redirect",
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as {
        commands: { posix: string };
      };
      expect(body.commands.posix).toContain("fix-the-login-redirect");
    });

    it("emits --autonomous when autonomy=autonomous and actionId is pipeline/iterate", async () => {
      const { task } = await createTask();
      const r = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actionId: "new-pipeline",
          autonomy: "autonomous",
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as { commands: { posix: string } };
      expect(body.commands.posix).toContain("--autonomous");
    });

    it("omits --autonomous when autonomy=guided", async () => {
      const { task } = await createTask();
      const r = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actionId: "new-pipeline",
          autonomy: "guided",
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as { commands: { posix: string } };
      expect(body.commands.posix).not.toContain("--autonomous");
    });

    it("persists phase/phaseLabel/description/autonomy/actionId onto the task", async () => {
      const { task } = await createTask();
      await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actionId: "new-task",
          phase: "compliance",
          phaseLabel: "Compliance",
          description: "audit drift",
          autonomy: "autonomous",
        }),
      });
      const get = await app.request(`/api/external/tasks/${task.taskId}`);
      expect(get.status).toBe(200);
      const body = (await get.json()) as {
        task: {
          phase?: string;
          phaseLabel?: string;
          description?: string;
          autonomy?: string;
          actionId?: string;
        };
      };
      expect(body.task.phase).toBe("compliance");
      expect(body.task.phaseLabel).toBe("Compliance");
      expect(body.task.description).toBe("audit drift");
      expect(body.task.autonomy).toBe("autonomous");
      expect(body.task.actionId).toBe("new-task");
    });

    it("falls back to legacy shape when actionId is missing (back-compat)", async () => {
      const { task } = await createTask();
      const r = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as { commands: { posix: string } };
      // Legacy shape: --session-id is always present; no slash command.
      expect(body.commands.posix).toContain("--session-id");
      expect(body.commands.posix).not.toContain("/shipwright-");
    });

    it("rejects unknown phase (InvalidPhase bubbles as 400)", async () => {
      const { task } = await createTask();
      const r = await app.request(`/api/external/tasks/${task.taskId}/launch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actionId: "new-task",
          phase: "not-a-real-phase",
          phaseLabel: "Fake",
        }),
      });
      expect(r.status).toBe(400);
    });
  });

  // ── 2026-04-23 — iterate-20260423-chat-livetest-2 AC-B ──
  // POST /tasks now persists phase on CREATION (not just on /launch per
  // ADR-046). Server derives phaseLabel from the validated actions catalog
  // (don't trust client-supplied label per external-review finding #2).
  describe("POST /tasks — phase persistence on creation (AC-B)", () => {
    it("persists phase + derived phaseLabel when body.phase matches the project's catalog", async () => {
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Audit drift",
          cwd: projectPath,
          projectId: PROJECT_ID,
          phase: "compliance",
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as {
        task: {
          taskId: string;
          phase?: string;
          phaseLabel?: string;
        };
      };
      expect(body.task.phase).toBe("compliance");
      // Derived from default-actions.json catalog entry, not from body.
      expect(body.task.phaseLabel).toBe("Compliance");
    });

    it("ignores client-supplied phaseLabel and re-derives from catalog (prevents label drift)", async () => {
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Drifted label test",
          cwd: projectPath,
          projectId: PROJECT_ID,
          phase: "build",
          phaseLabel: "WRONG_LABEL_FROM_CLIENT",
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as {
        task: { phase?: string; phaseLabel?: string };
      };
      expect(body.task.phase).toBe("build");
      // Server authoritatively derives from the catalog — client label dropped.
      expect(body.task.phaseLabel).toBe("Build");
      expect(body.task.phaseLabel).not.toBe("WRONG_LABEL_FROM_CLIENT");
    });

    it("returns 400 invalid_phase with allowed[] when phase is not in the catalog", async () => {
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Bad phase test",
          cwd: projectPath,
          projectId: PROJECT_ID,
          phase: "not-a-real-phase",
        }),
      });
      expect(r.status).toBe(400);
      const body = (await r.json()) as {
        error: string;
        detail?: string;
        allowed?: string[];
      };
      expect(body.error).toBe("invalid_phase");
      expect(body.detail).toContain("not-a-real-phase");
      expect(Array.isArray(body.allowed)).toBe(true);
      expect(body.allowed!.length).toBeGreaterThan(5);
      expect(body.allowed).toContain("compliance");
    });

    it("creates task with phase=null when body.phase is omitted (back-compat)", async () => {
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Legacy create",
          cwd: projectPath,
          projectId: PROJECT_ID,
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as {
        task: { phase?: string; phaseLabel?: string };
      };
      expect(body.task.phase).toBeUndefined();
      expect(body.task.phaseLabel).toBeUndefined();
    });

    it("persists phase + phaseLabel through GET /tasks list (end-to-end serializer trace)", async () => {
      // GPT review #1 HIGH — verify phase survives store → persist →
      // JSON serialization → list response. Create then list.
      await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Round-trip test",
          cwd: projectPath,
          projectId: PROJECT_ID,
          phase: "design",
        }),
      });
      const list = await app.request("/api/external/tasks");
      expect(list.status).toBe(200);
      const body = (await list.json()) as {
        tasks: Array<{
          title: string;
          phase?: string;
          phaseLabel?: string;
        }>;
      };
      const row = body.tasks.find((t) => t.title === "Round-trip test");
      expect(row).toBeDefined();
      expect(row!.phase).toBe("design");
      expect(row!.phaseLabel).toBe("Design");
    });

    it("rejects with 400 phase_requires_project when phase is sent without projectId", async () => {
      // Code-review blocker #2 / Gemini #2: never silently drop user input.
      // Unassigned projects have no catalog to validate against — if the
      // client sends phase anyway, it's a bug; surface it rather than
      // persisting silently. Callers without a project must omit phase.
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Unassigned task",
          cwd: projectPath,
          phase: "compliance",
        }),
      });
      expect(r.status).toBe(400);
      const body = (await r.json()) as { error: string; detail: string };
      expect(body.error).toBe("phase_requires_project");
    });

    it("still accepts creation without phase (back-compat) for unassigned projects", async () => {
      const r = await app.request("/api/external/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Unassigned task no phase",
          cwd: projectPath,
        }),
      });
      expect(r.status).toBe(200);
      const body = (await r.json()) as {
        task: { phase?: string; projectId: string };
      };
      expect(body.task.projectId).toBe("unassigned");
      expect(body.task.phase).toBeUndefined();
    });
  });
});
