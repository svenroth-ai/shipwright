import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createChatRoutes } from "./chat.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };
const mockMessages = [{ id: "m1", taskId: "t1", type: "assistant", content: "Hello", timestamp: "2026-01-01T00:00:00Z" }];

function setup({ existingProcess = false, acquireResult = "ok" as "ok" | "queued", hasSession = true } = {}) {
  const chatStore = { load: vi.fn(async () => mockMessages), append: vi.fn(async () => {}) } as any;
  const governor = {
    getProcess: vi.fn(() => existingProcess ? { pid: 123, state: "running" } : undefined),
    acquire: vi.fn(async () => acquireResult === "queued" ? "queued" : { pid: 456, state: "running" }),
  } as any;
  const adapter = {} as any;
  const projectManager = { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) } as any;
  const taskManager = { getTaskById: vi.fn(() => ({ id: "t1", sessionId: "sess-abc" })) } as any;
  const eventStore = { addEvent: vi.fn() } as any;
  const sseManager = { broadcast: vi.fn() } as any;
  const sessionRegistry = {
    get: vi.fn(() => hasSession ? "real-claude-session-id" : undefined),
    set: vi.fn(async () => {}),
  } as any;

  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createChatRoutes(chatStore, governor, adapter, projectManager, taskManager, eventStore, sseManager, sessionRegistry));
  return { app, chatStore, governor, eventStore, sseManager, sessionRegistry };
}

describe("Chat Routes", () => {
  it("GET /api/projects/:id/chat/:taskId returns messages", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/chat/t1");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
  });

  it("POST /api/projects/:id/chat spawns a new Claude process with --resume", async () => {
    const { app, governor, chatStore } = setup();
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hello" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.type).toBe("user");
    expect(body.data.content).toBe("Hello");

    // User message was persisted
    expect(chatStore.append).toHaveBeenCalled();

    // governor.acquire was called with resume: "explicit" and the REAL Claude session id
    expect(governor.acquire).toHaveBeenCalledWith(
      expect.objectContaining({
        taskId: "t1",
        sessionId: "real-claude-session-id",
        resume: "explicit",
        prompt: "Hello",
      }),
    );
  });

  it("POST /api/projects/:id/chat returns 409 if no session recorded yet", async () => {
    const { app } = setup({ hasSession: false });
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hi" }),
    });
    expect(res.status).toBe(409);
  });

  it("POST /api/projects/:id/chat emits phase_started event", async () => {
    const { app, eventStore, sseManager } = setup();
    await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hi" }),
    });
    expect(eventStore.addEvent).toHaveBeenCalledWith(
      "p1",
      expect.objectContaining({ type: "phase_started", task_id: "t1", phase: "build" }),
    );
    expect(sseManager.broadcast).toHaveBeenCalled();
  });

  it("POST /api/projects/:id/chat returns 409 if a process is still running", async () => {
    const { app } = setup({ existingProcess: true });
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hi" }),
    });
    expect(res.status).toBe(409);
  });

  it("POST /api/projects/:id/chat rejects empty message", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1" }),
    });
    expect(res.status).toBe(400);
  });
});
