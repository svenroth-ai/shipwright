import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createTaskRoutes } from "./tasks.js";
import { errorHandler } from "../middleware/error-handler.js";

vi.mock("../bridge/intent-classifier.js", async () => {
  const actual = await vi.importActual<typeof import("../bridge/intent-classifier.js")>(
    "../bridge/intent-classifier.js"
  );
  return {
    ...actual,
    classifyPhase: vi.fn(async () => ({ phase: "build", confidence: 0.8 })),
  };
});

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };
const mockTask = { id: "t1", projectId: "p1", description: "Fix", status: "pending", kanbanStatus: "backlog", sessionId: "s1", createdAt: "2026-01-01", updatedAt: "2026-01-01" };

function setup(queueFull = false, opts: {
  runningProcess?: {
    state?: string;
    claudeSessionId?: string;
  } | null;
  pendingInboxForTask?: string | null;
} = {}) {
  const runningProcess = opts.runningProcess === null
    ? undefined
    : {
        pid: 123,
        taskId: "t1",
        state: opts.runningProcess?.state ?? "running",
        claudeSessionId: opts.runningProcess?.claudeSessionId,
        ...opts.runningProcess,
      };
  const deps = {
    taskManager: {
      getTasksWithKanban: vi.fn(() => [mockTask]),
      getTaskById: vi.fn((pid: string, tid: string) => tid === "t1" ? mockTask : undefined),
    },
    eventStore: { addEvent: vi.fn() },
    governor: {
      acquire: vi.fn(async () => queueFull ? "queued" : { pid: 123, taskId: "t1" }),
      getProcess: vi.fn((tid: string) => (tid === "t1" && runningProcess ? runningProcess : undefined)),
      release: vi.fn(async () => {}),
    },
    adapter: {
      terminate: vi.fn(),
    },
    sseManager: { broadcast: vi.fn() },
    projectManager: { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) },
    inboxManager: {
      getByProject: vi.fn(() => {
        if (!opts.pendingInboxForTask) return [];
        return [{ id: "inbox1", projectId: "p1", taskId: opts.pendingInboxForTask, status: "pending" }];
      }),
    },
    emitTaskCreatedEvent: vi.fn(async () => ({})),
    emitTaskCancelledEvent: vi.fn(async () => ({})),
    emitWorkCompletedEvent: vi.fn(async () => ({})),
    emitTaskUpdatedEvent: vi.fn(async () => ({})),
  } as any;
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createTaskRoutes(deps));
  return { app, deps };
}

describe("Task Routes", () => {
  it("GET /api/projects/:id/tasks returns tasks with kanbanStatus", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data[0]).toHaveProperty("kanbanStatus");
  });

  it("POST /api/projects/:id/tasks returns 201", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "New task" }),
    });
    expect(res.status).toBe(201);
  });

  it("POST when governor full returns 202", async () => {
    const { app } = setup(true);
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Queued task" }),
    });
    expect(res.status).toBe(202);
  });

  // Iterate 10 — mid-task permission mode switching
  it("POST /tasks/:id/mode respawns with --resume + new permissionMode", async () => {
    const { app, deps } = setup(false, {
      runningProcess: { state: "running", claudeSessionId: "real-claude-sess-xyz" },
    });
    const res = await app.request("/api/projects/p1/tasks/t1/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "plan" }),
    });
    expect(res.status).toBe(200);
    expect(deps.adapter.terminate).toHaveBeenCalledTimes(1);
    expect(deps.governor.release).toHaveBeenCalledWith("t1");
    expect(deps.governor.acquire).toHaveBeenCalledTimes(1);
    const opts = deps.governor.acquire.mock.calls[0][0];
    expect(opts.sessionId).toBe("real-claude-sess-xyz");
    expect(opts.resumeSession).toBe(true);
    expect(opts.permissionMode).toBe("plan");
  });

  it("POST /tasks/:id/mode returns 409 when a pending inbox item exists", async () => {
    const { app, deps } = setup(false, {
      runningProcess: { state: "running", claudeSessionId: "real-claude-sess-xyz" },
      pendingInboxForTask: "t1",
    });
    const res = await app.request("/api/projects/p1/tasks/t1/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "plan" }),
    });
    expect(res.status).toBe(409);
    const body = await res.json();
    expect(body.error).toMatch(/pending question|Answer/i);
    expect(deps.adapter.terminate).not.toHaveBeenCalled();
  });

  it("POST /tasks/:id/mode returns 409 when session_id not yet captured", async () => {
    const { app, deps } = setup(false, {
      runningProcess: { state: "running", claudeSessionId: undefined },
    });
    const res = await app.request("/api/projects/p1/tasks/t1/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "acceptEdits" }),
    });
    expect(res.status).toBe(409);
    expect(deps.adapter.terminate).not.toHaveBeenCalled();
  });

  it("POST /tasks/:id/mode returns 400 when process is not running", async () => {
    const { app } = setup(false, { runningProcess: null });
    const res = await app.request("/api/projects/p1/tasks/t1/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "plan" }),
    });
    expect(res.status).toBe(400);
  });

  it("POST /tasks/:id/mode validates the mode enum (unknown rejected as 400)", async () => {
    const { app } = setup(false, {
      runningProcess: { state: "running", claudeSessionId: "real-claude-sess-xyz" },
    });
    const res = await app.request("/api/projects/p1/tasks/t1/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "turbo-mode" }),
    });
    expect(res.status).toBe(400);
  });

  // Iterate 9 — model + effort wire-through
  it("POST /tasks forwards body.model to governor.acquire as model option", async () => {
    const { app, deps } = setup();
    await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Build auth", model: "sonnet" }),
    });
    expect(deps.governor.acquire).toHaveBeenCalled();
    const opts = deps.governor.acquire.mock.calls[0][0];
    expect(opts.model).toBe("sonnet");
  });

  it("POST /tasks omits model when body.model is invalid", async () => {
    const { app, deps } = setup();
    await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Build auth", model: "bananasaurus" }),
    });
    const opts = deps.governor.acquire.mock.calls[0][0];
    expect(opts.model).toBeUndefined();
  });

  it("POST /tasks ignores body.effort (CLI 2.1.1 no longer exposes thinking slash commands)", async () => {
    const { app, deps } = setup();
    await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Design the auth layer", effort: "high" }),
    });
    const opts = deps.governor.acquire.mock.calls[0][0];
    expect(opts.prompt).not.toMatch(/^\//);
    expect(opts.prompt).toContain("Design the auth layer");
  });

  it("PATCH task status with cancelled returns updated", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks/t1/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "cancelled" }),
    });
    expect(res.status).toBe(200);
  });

  // Iterate 8 — task_cancelled / work_completed / task_updated must persist to disk
  // so deleted / closed / edited tasks survive a server restart.
  it("PATCH status=cancelled persists task_cancelled via emitTaskCancelledEvent", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks/t1/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "cancelled" }),
    });
    expect(res.status).toBe(200);
    expect(deps.emitTaskCancelledEvent).toHaveBeenCalledTimes(1);
    const [filePath, taskId, projectId] = deps.emitTaskCancelledEvent.mock.calls[0];
    expect(filePath).toMatch(/shipwright_events\.jsonl$/);
    expect(taskId).toBe("t1");
    expect(projectId).toBe("p1");
  });

  it("PATCH status=closed persists work_completed via emitWorkCompletedEvent", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks/t1/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "closed" }),
    });
    expect(res.status).toBe(200);
    expect(deps.emitWorkCompletedEvent).toHaveBeenCalledTimes(1);
    expect(deps.emitTaskCancelledEvent).not.toHaveBeenCalled();
  });

  it("PATCH description persists task_updated via emitTaskUpdatedEvent", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks/t1/description", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Updated body" }),
    });
    expect(res.status).toBe(200);
    expect(deps.emitTaskUpdatedEvent).toHaveBeenCalledTimes(1);
    const [, taskId, projectId, fields] = deps.emitTaskUpdatedEvent.mock.calls[0];
    expect(taskId).toBe("t1");
    expect(projectId).toBe("p1");
    expect(fields).toEqual({ description: "Updated body" });
  });

  it("PATCH non-existent task returns 404", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks/t99/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "cancelled" }),
    });
    expect(res.status).toBe(404);
  });

  it("POST with startImmediately=false does not call governor.acquire", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Deferred task", startImmediately: false }),
    });
    expect(res.status).toBe(201);
    expect(deps.governor.acquire).not.toHaveBeenCalled();
  });

  it("POST succeeds even when governor.acquire throws", async () => {
    const deps = {
      taskManager: { getTasksWithKanban: vi.fn(() => []), getTaskById: vi.fn() },
      eventStore: { addEvent: vi.fn() },
      governor: { acquire: vi.fn(async () => { throw new Error("Claude CLI not found"); }) },
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject), getAll: vi.fn(() => [mockProject]) },
      emitTaskCreatedEvent: vi.fn(async () => ({})),
    } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createTaskRoutes(deps));

    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Resilient task" }),
    });
    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.startStatus).toBe("failed");
  });

  it("POST /tasks to unknown project returns 404", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/unknown/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Orphaned" }),
    });
    expect(res.status).toBe(404);
  });

  it("POST /tasks without description returns 400", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });

  it("POST /tasks/:taskId/start on unknown task returns 404", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks/t99/start", { method: "POST" });
    expect(res.status).toBe(404);
  });

  it("POST /tasks/:taskId/start on existing task succeeds", async () => {
    const deps = {
      taskManager: { getTasksWithKanban: vi.fn(() => [mockTask]), getTaskById: vi.fn(() => mockTask) },
      eventStore: { addEvent: vi.fn() },
      governor: { acquire: vi.fn(async () => ({ pid: 456 })), getProcess: vi.fn(() => undefined) },
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject) },
      emitTaskCreatedEvent: vi.fn(async () => ({})),
    } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createTaskRoutes(deps));

    const res = await app.request("/api/projects/p1/tasks/t1/start", { method: "POST" });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.status).toBe("running");
  });

  it("POST /tasks/:taskId/start when already running returns 409", async () => {
    const deps = {
      taskManager: { getTasksWithKanban: vi.fn(() => [mockTask]), getTaskById: vi.fn(() => mockTask) },
      eventStore: { addEvent: vi.fn() },
      governor: { acquire: vi.fn(), getProcess: vi.fn(() => ({ state: "running" })) },
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject) },
      emitTaskCreatedEvent: vi.fn(async () => ({})),
    } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createTaskRoutes(deps));

    const res = await app.request("/api/projects/p1/tasks/t1/start", { method: "POST" });
    expect(res.status).toBe(409);
  });

  it("PATCH with invalid status returns 400", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks/t1/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "invalid" }),
    });
    expect(res.status).toBe(400);
  });

  it("POST /tasks with explicit phase emits phase_started with that phase", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Sketch the hero area", phase: "design" }),
    });
    expect(res.status).toBe(201);
    const phaseEvent = deps.eventStore.addEvent.mock.calls.find(
      ([, ev]: [string, { type: string }]) => ev.type === "phase_started"
    );
    expect(phaseEvent).toBeDefined();
    expect(phaseEvent[1].phase).toBe("design");
  });

  it("POST /tasks without phase auto-classifies and emits phase_started", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "implement auth hook" }),
    });
    expect(res.status).toBe(201);
    const phaseEvent = deps.eventStore.addEvent.mock.calls.find(
      ([, ev]: [string, { type: string }]) => ev.type === "phase_started"
    );
    expect(phaseEvent).toBeDefined();
    // Mocked classifyPhase returns "build"
    expect(phaseEvent[1].phase).toBe("build");
  });

  it("POST /tasks/:taskId/start uses task.requestedPhase when set", async () => {
    const taskWithPhase = { ...mockTask, requestedPhase: "design" };
    const deps = {
      taskManager: {
        getTasksWithKanban: vi.fn(() => [taskWithPhase]),
        getTaskById: vi.fn(() => taskWithPhase),
      },
      eventStore: { addEvent: vi.fn() },
      governor: { acquire: vi.fn(async () => ({ pid: 456 })), getProcess: vi.fn(() => undefined) },
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject) },
      emitTaskCreatedEvent: vi.fn(async () => ({})),
    } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createTaskRoutes(deps));

    const res = await app.request("/api/projects/p1/tasks/t1/start", { method: "POST" });
    expect(res.status).toBe(200);
    const phaseEvent = deps.eventStore.addEvent.mock.calls.find(
      ([, ev]: [string, { type: string }]) => ev.type === "phase_started"
    );
    expect(phaseEvent).toBeDefined();
    expect(phaseEvent[1].phase).toBe("design");
  });

  it("POST /tasks/:taskId/start falls back to classifyPhase when requestedPhase missing", async () => {
    const taskNoPhase = { ...mockTask, title: "implement auth hook", description: "" };
    const deps = {
      taskManager: {
        getTasksWithKanban: vi.fn(() => [taskNoPhase]),
        getTaskById: vi.fn(() => taskNoPhase),
      },
      eventStore: { addEvent: vi.fn() },
      governor: { acquire: vi.fn(async () => ({ pid: 456 })), getProcess: vi.fn(() => undefined) },
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject) },
      emitTaskCreatedEvent: vi.fn(async () => ({})),
    } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createTaskRoutes(deps));

    const res = await app.request("/api/projects/p1/tasks/t1/start", { method: "POST" });
    expect(res.status).toBe(200);
    const phaseEvent = deps.eventStore.addEvent.mock.calls.find(
      ([, ev]: [string, { type: string }]) => ev.type === "phase_started"
    );
    // Mocked classifyPhase returns "build"
    expect(phaseEvent[1].phase).toBe("build");
  });

  it("POST /tasks with explicit phase persists it on task_created event", async () => {
    const { app } = setup();
    const writerCalls: Array<{ phase?: string }> = [];
    // capture via emitTaskCreatedEvent shim
    const deps2 = {
      taskManager: {
        getTasksWithKanban: vi.fn(() => [mockTask]),
        getTaskById: vi.fn(() => mockTask),
      },
      eventStore: { addEvent: vi.fn() },
      governor: { acquire: vi.fn(async () => ({ pid: 123 })) },
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject) },
      emitTaskCreatedEvent: vi.fn(async (...args: unknown[]) => {
        // The 7th positional arg is phase
        const phase = args[6] as string | undefined;
        writerCalls.push({ phase });
        return {};
      }),
    } as any;
    const app2 = new Hono();
    app2.onError(errorHandler);
    app2.route("/", createTaskRoutes(deps2));
    const res = await app2.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "design hero", phase: "design" }),
    });
    expect(res.status).toBe(201);
    expect(writerCalls).toHaveLength(1);
    expect(writerCalls[0].phase).toBe("design");
    void app;
  });

  it("POST /tasks with invalid phase falls back to auto-classification", async () => {
    const { app, deps } = setup();
    const res = await app.request("/api/projects/p1/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "anything", phase: "bogus-phase" }),
    });
    expect(res.status).toBe(201);
    const phaseEvent = deps.eventStore.addEvent.mock.calls.find(
      ([, ev]: [string, { type: string }]) => ev.type === "phase_started"
    );
    expect(phaseEvent[1].phase).toBe("build");
  });

  it("GET /api/tasks returns tasks from all projects", async () => {
    const deps = {
      taskManager: { getTasksWithKanban: vi.fn(() => [mockTask]) },
      eventStore: { addEvent: vi.fn() },
      governor: {},
      adapter: {},
      sseManager: { broadcast: vi.fn() },
      projectManager: { getById: vi.fn(() => mockProject), getAll: vi.fn(() => [mockProject]) },
      emitTaskCreatedEvent: vi.fn(async () => ({})),
    } as any;
    const app = new Hono();
    app.route("/", createTaskRoutes(deps));

    const res = await app.request("/api/tasks");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
  });

  // Iterate 14.1 — POST /api/projects/:id/preview spawns /shipwright-preview
  describe("POST /api/projects/:id/preview (iterate 14.1)", () => {
    function setupPreview(hasPreview: boolean | undefined) {
      const project = { ...mockProject, hasPreview };
      const deps = {
        taskManager: { getTasksWithKanban: vi.fn(() => []) },
        eventStore: { addEvent: vi.fn() },
        governor: { acquire: vi.fn(async () => ({ pid: 123, taskId: "preview-t" })) },
        adapter: {},
        sseManager: { broadcast: vi.fn() },
        projectManager: { getById: vi.fn((id: string) => id === "p1" ? project : undefined) },
        emitTaskCreatedEvent: vi.fn(async () => ({})),
        emitPhaseStartedEvent: vi.fn(async () => ({})),
      } as any;
      const app = new Hono();
      app.onError(errorHandler);
      app.route("/", createTaskRoutes(deps));
      return { app, deps };
    }

    it("returns 202 with taskId when project has preview capability", async () => {
      const { app, deps } = setupPreview(true);
      const res = await app.request("/api/projects/p1/preview", { method: "POST" });
      expect(res.status).toBe(202);
      const body = await res.json() as any;
      expect(body.data.taskId).toBeDefined();
      expect(body.data.startStatus).toBe("started");
      // Governor spawned with the /shipwright-preview slash command as prompt
      expect(deps.governor.acquire).toHaveBeenCalledTimes(1);
      const acquireArgs = deps.governor.acquire.mock.calls[0][0];
      expect(acquireArgs.prompt).toBe("/shipwright-preview");
      expect(deps.emitTaskCreatedEvent).toHaveBeenCalled();
    });

    it("returns 403 when project lacks preview capability", async () => {
      const { app, deps } = setupPreview(false);
      const res = await app.request("/api/projects/p1/preview", { method: "POST" });
      expect(res.status).toBe(403);
      expect(deps.governor.acquire).not.toHaveBeenCalled();
    });

    it("returns 403 when hasPreview is undefined", async () => {
      const { app, deps } = setupPreview(undefined);
      const res = await app.request("/api/projects/p1/preview", { method: "POST" });
      expect(res.status).toBe(403);
      expect(deps.governor.acquire).not.toHaveBeenCalled();
    });

    it("returns 404 when project not found", async () => {
      const { app } = setupPreview(true);
      const res = await app.request("/api/projects/nonexistent/preview", { method: "POST" });
      expect(res.status).toBe(404);
    });
  });
});
