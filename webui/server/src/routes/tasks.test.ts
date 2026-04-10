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
});
