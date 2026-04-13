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
  // Iterate 11.2 — "latest pending per task" (reverts 11.1 zombie filter,
  // replaces with a rule that handles both symptoms)
  // ──────────────────────────────────────────────────────────────────

  it("GET /api/inbox keeps only the LATEST pending item per task", async () => {
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
    expect(body.data[0].id).toBe("t1-newest");
  });

  it("GET /api/inbox keeps one latest item per task across multiple tasks", async () => {
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
    expect(ids).toEqual(["t1-newest", "t2-newest"]);
  });

  it("GET /api/inbox shows items for running tasks even when governor has no live process (no more 11.1 zombie filter)", async () => {
    const inboxManager = {
      getAll: vi.fn(() => [{ ...mockItem, id: "shown-anyway", taskId: "t1", status: "pending" }]),
    } as any;
    const taskManager = {
      getTaskById: vi.fn(() => ({ id: "t1", status: "running" })),
    } as any;
    const projectManager = { getById: vi.fn() } as any;
    // Governor says no live process. Iterate 11.2 IGNORES this — item still shown.
    const governor = {
      getProcess: vi.fn(() => undefined),
    } as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager, governor));

    const res = await app.request("/api/inbox");
    const body = await res.json();
    expect(body.data).toHaveLength(1);
    expect(body.data[0].id).toBe("shown-anyway");
  });

  it("GET /api/inbox preserves answered items alongside the latest pending", async () => {
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
    expect(ids).toEqual(["t1-answered", "t1-pending-new"]);
  });
});
