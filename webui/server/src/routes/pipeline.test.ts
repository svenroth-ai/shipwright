import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createPipelineRoutes } from "./pipeline.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };

function setup() {
  const eventStore = {
    getPipelineState: vi.fn(() => [
      { name: "project", status: "completed" },
      { name: "design", status: "completed" },
      { name: "plan", status: "completed" },
      { name: "build", status: "running" },
      { name: "test", status: "pending" },
      { name: "changelog", status: "pending" },
      { name: "deploy", status: "pending" },
    ]),
  } as any;
  const projectManager = { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) } as any;
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createPipelineRoutes(eventStore, projectManager));
  return { app };
}

describe("Pipeline Routes", () => {
  it("GET /api/projects/:id/pipeline returns 7 phases", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/pipeline");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.phases).toHaveLength(7);
  });
});
