import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createTaskRoutes } from "./tasks.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };
const mockTask = { id: "t1", projectId: "p1", description: "Fix", status: "pending", kanbanStatus: "backlog", sessionId: "s1", createdAt: "2026-01-01", updatedAt: "2026-01-01" };

function setup(queueFull = false) {
  const deps = {
    taskManager: {
      getTasksWithKanban: vi.fn(() => [mockTask]),
      getTaskById: vi.fn((pid: string, tid: string) => tid === "t1" ? mockTask : undefined),
    },
    eventStore: { addEvent: vi.fn() },
    governor: { acquire: vi.fn(async () => queueFull ? "queued" : { pid: 123, taskId: "t1" }) },
    adapter: {},
    sseManager: { broadcast: vi.fn() },
    projectManager: { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) },
    emitTaskCreatedEvent: vi.fn(async () => ({})),
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

  it("PATCH task status with cancelled returns updated", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/tasks/t1/status", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "cancelled" }),
    });
    expect(res.status).toBe(200);
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
});
