import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createDocsRoutes } from "./docs.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp/testproj", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };

function setup() {
  const projectManager = { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) } as any;
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createDocsRoutes(projectManager));
  return { app };
}

describe("Docs Routes", () => {
  // Note: These tests verify route wiring. Full file tree and content tests
  // would need actual filesystem fixtures. Route tests verify the API contract.
  it("GET /api/projects/:id/docs returns 200 for existing project", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/docs");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toBeDefined();
  });

  it("GET /api/projects/nonexistent/docs returns 404", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/nonexistent/docs");
    expect(res.status).toBe(404);
  });
});
