import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createChatRoutes } from "./chat.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };
const mockMessages = [{ id: "m1", taskId: "t1", type: "assistant", content: "Hello", timestamp: "2026-01-01T00:00:00Z" }];

function setup({ procState = "running" as "running" | "exited" | null } = {}) {
  const chatStore = { load: vi.fn(async () => mockMessages), append: vi.fn(async () => {}) } as any;
  const mockProc = procState === null ? undefined : { pid: 123, state: procState };
  const governor = { getProcess: vi.fn(() => mockProc) } as any;
  const adapter = { sendUserMessage: vi.fn() } as any;
  const projectManager = { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) } as any;

  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createChatRoutes(chatStore, governor, adapter, projectManager));
  return { app, chatStore, governor, adapter };
}

describe("Chat Routes", () => {
  it("GET /api/projects/:id/chat/:taskId returns messages", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/chat/t1");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
  });

  it("POST /api/projects/:id/chat sends text message via sendUserMessage", async () => {
    const { app, adapter, chatStore } = setup();
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

    // sendUserMessage was called with the plain string
    expect(adapter.sendUserMessage).toHaveBeenCalledWith(
      expect.objectContaining({ pid: 123 }),
      "Hello",
    );
  });

  it("POST /api/projects/:id/chat sends multimodal (text + image) as content blocks", async () => {
    const { app, adapter } = setup();
    await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        taskId: "t1",
        message: "Look at this",
        images: [{ media_type: "image/png", data: "base64data" }],
      }),
    });
    expect(adapter.sendUserMessage).toHaveBeenCalledWith(
      expect.anything(),
      [
        { type: "text", text: "Look at this" },
        {
          type: "image",
          source: { type: "base64", media_type: "image/png", data: "base64data" },
        },
      ],
    );
  });

  it("POST /api/projects/:id/chat returns 400 if process not running", async () => {
    const { app } = setup({ procState: null });
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hi" }),
    });
    expect(res.status).toBe(400);
  });

  it("POST /api/projects/:id/chat returns 400 if process has exited", async () => {
    const { app } = setup({ procState: "exited" });
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1", message: "Hi" }),
    });
    expect(res.status).toBe(400);
  });

  it("POST /api/projects/:id/chat rejects when neither message nor images", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ taskId: "t1" }),
    });
    expect(res.status).toBe(400);
  });
});
