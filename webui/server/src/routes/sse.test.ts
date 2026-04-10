import { describe, it, expect } from "vitest";
import { Hono } from "hono";
import { createSSERoute } from "./sse.js";
import { SSEManager } from "../core/sse-manager.js";

describe("SSE Route", () => {
  function createApp() {
    const sseManager = new SSEManager();
    const app = new Hono();
    app.route("/", createSSERoute(sseManager));
    return { app, sseManager };
  }

  it("GET /api/events returns 200", async () => {
    const { app } = createApp();
    const res = await app.request("/api/events");
    expect(res.status).toBe(200);
  });

  it("response has text/event-stream content type", async () => {
    const { app } = createApp();
    const res = await app.request("/api/events");
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
  });

  it("response has no-cache header", async () => {
    const { app } = createApp();
    const res = await app.request("/api/events");
    expect(res.headers.get("Cache-Control")).toBe("no-cache");
  });

  it("response body is a readable stream", async () => {
    const { app } = createApp();
    const res = await app.request("/api/events");
    expect(res.body).toBeTruthy();
  });
});
