import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createChatRoutes } from "./chat.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };
const mockMessages = [{ id: "m1", taskId: "t1", type: "assistant", content: "Hello", timestamp: "2026-01-01T00:00:00Z" }];

function setup() {
  const chatStore = { load: vi.fn(async () => mockMessages), append: vi.fn(async () => {}) } as any;
  const governor = { getProcess: vi.fn(() => ({ pid: 123, state: "running" })) } as any;
  const adapter = { sendStdin: vi.fn() } as any;
  const projectManager = { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) } as any;
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createChatRoutes(chatStore, governor, adapter, projectManager));
  return { app };
}

describe("Chat Routes", () => {
  it("GET /api/projects/:id/chat/:taskId returns messages", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/chat/t1");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
  });

  it("POST /api/projects/:id/chat sends message", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hello" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.type).toBe("user");
  });
});
