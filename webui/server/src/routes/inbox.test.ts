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
});
