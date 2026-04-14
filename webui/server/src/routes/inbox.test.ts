import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createInboxRoutes } from "./inbox.js";
import { errorHandler, AppError } from "../middleware/error-handler.js";

const mockItem = { id: "i1", projectId: "p1", taskId: "t1", question: "Continue?", status: "pending", createdAt: "2026-01-01" };

function setup() {
  const inboxManager = {
    getAll: vi.fn((filter?: { status?: string }) => {
      if (filter?.status === "pending") return [mockItem];
      return [mockItem, { ...mockItem, id: "i2", status: "answered" }];
    }),
    answer: vi.fn((id: string) => {
      if (id === "answered") throw new AppError("Already answered", 400);
      return { ...mockItem, status: "answered", answer: "yes" };
    }),
  } as any;
  const sseManager = { broadcast: vi.fn() } as any;
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createInboxRoutes(inboxManager, sseManager));
  return { app };
}

describe("Inbox Routes", () => {
  it("GET /api/inbox returns all items", async () => {
    const { app } = setup();
    const res = await app.request("/api/inbox");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(2);
  });

  it("GET /api/inbox?status=pending returns filtered", async () => {
    const { app } = setup();
    const res = await app.request("/api/inbox?status=pending");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
  });

  it("POST /api/inbox/:id/answer returns answered item", async () => {
    const { app } = setup();
    const res = await app.request("/api/inbox/i1/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: "yes" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.status).toBe("answered");
  });

  it("POST already-answered returns 400", async () => {
    const { app } = setup();
    const res = await app.request("/api/inbox/answered/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: "no" }),
    });
    expect(res.status).toBe(400);
  });

  // ──────────────────────────────────────────────────────────────────
  // Iterate 11 — filter out items whose task is terminal or gone
  // ──────────────────────────────────────────────────────────────────

  it("GET /api/inbox filters items whose task does not exist", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "alive", taskId: "t-alive" },
        { ...mockItem, id: "ghost", taskId: "t-missing" },
      ]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn((_pid: string, tid: string) =>
        tid === "t-alive" ? { id: tid, status: "running" } : undefined,
      ),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].id).toBe("alive");
  });

  it("GET /api/inbox filters items whose task is in a terminal status", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "pending-task", taskId: "t1" },
        { ...mockItem, id: "done-task", taskId: "t2" },
        { ...mockItem, id: "cancelled-task", taskId: "t3" },
        { ...mockItem, id: "failed-task", taskId: "t4" },
        { ...mockItem, id: "running-task", taskId: "t5" },
      ]),
    } as any;
    const taskStatuses: Record<string, string> = {
      t1: "pending",
      t2: "done",
      t3: "cancelled",
      t4: "failed",
      t5: "running",
    };
    const taskManager = {
      getTaskById: vi.fn((_pid: string, tid: string) =>
        taskStatuses[tid] ? { id: tid, status: taskStatuses[tid] } : undefined,
      ),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    const ids = body.data.map((i: { id: string }) => i.id).sort();
    expect(ids).toEqual(["pending-task", "running-task"]);
  });

  it("GET /api/inbox returns all items when taskManager is not wired (backwards compat)", async () => {
    const { app } = setup();
    const res = await app.request("/api/inbox");
    const body = await res.json();
    expect(body.data).toHaveLength(2);
  });

  // ──────────────────────────────────────────────────────────────────
  // Iterate 11.3 — "first pending per task" (reverts 11.2 latest-wins
  // to oldest-wins: show the question Claude opened the interview with)
  // ──────────────────────────────────────────────────────────────────

  it("GET /api/inbox keeps only the FIRST pending item per task (oldest createdAt wins)", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "t1-old",    taskId: "t1", status: "pending", createdAt: "2026-04-13T10:00:00Z", question: "Plattform?" },
        { ...mockItem, id: "t1-newer",  taskId: "t1", status: "pending", createdAt: "2026-04-13T11:00:00Z", question: "Tech-Stack?" },
        { ...mockItem, id: "t1-newest", taskId: "t1", status: "pending", createdAt: "2026-04-13T12:00:00Z", question: "Datenbank?" },
      ]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn(() => ({ id: "t1", status: "running" })),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].id).toBe("t1-old");
  });

  it("GET /api/inbox collapses same-turn duplicates with identical stale timestamps to the first inserted", async () => {
    const staleTs = "2026-04-13T10:00:00Z";
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "t1-first",  taskId: "t1", status: "pending", createdAt: staleTs, question: "Was für eine App?" },
        { ...mockItem, id: "t1-second", taskId: "t1", status: "pending", createdAt: staleTs, question: "Was für eine App!" },
      ]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn(() => ({ id: "t1", status: "running" })),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].id).toBe("t1-first");
  });

  it("GET /api/inbox returns a single pending item unchanged", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "solo", taskId: "t1", status: "pending", createdAt: "2026-04-13T10:00:00Z" },
      ]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn(() => ({ id: "t1", status: "running" })),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].id).toBe("solo");
  });

  it("GET /api/inbox keeps one first item per task across multiple tasks", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "t1-old",    taskId: "t1", status: "pending", createdAt: "2026-04-13T10:00:00Z" },
        { ...mockItem, id: "t1-newest", taskId: "t1", status: "pending", createdAt: "2026-04-13T11:00:00Z" },
        { ...mockItem, id: "t2-old",    taskId: "t2", status: "pending", createdAt: "2026-04-13T10:30:00Z" },
        { ...mockItem, id: "t2-newest", taskId: "t2", status: "pending", createdAt: "2026-04-13T11:30:00Z" },
      ]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn((_pid: string, tid: string) => ({ id: tid, status: "running" })),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    const ids = body.data.map((i: { id: string }) => i.id).sort();
    expect(ids).toEqual(["t1-old", "t2-old"]);
  });

  it("GET /api/inbox preserves answered items alongside the first pending", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [
        { ...mockItem, id: "t1-answered",    taskId: "t1", status: "answered", createdAt: "2026-04-13T09:00:00Z" },
        { ...mockItem, id: "t1-pending-old", taskId: "t1", status: "pending",  createdAt: "2026-04-13T10:00:00Z" },
        { ...mockItem, id: "t1-pending-new", taskId: "t1", status: "pending",  createdAt: "2026-04-13T11:00:00Z" },
      ]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn(() => ({ id: "t1", status: "running" })),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    const ids = body.data.map((i: { id: string }) => i.id).sort();
    expect(ids).toEqual(["t1-answered", "t1-pending-old"]);
  });
});
