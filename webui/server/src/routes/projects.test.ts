import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createProjectRoutes } from "./projects.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = {
  id: "p1",
  name: "Test",
  path: "/tmp",
  profile: "default",
  status: "active",
  createdAt: "2026-01-01",
  lastActive: "2026-01-01",
};

function setup() {
  const projectManager = {
    getAll: vi.fn(() => [mockProject]),
    getById: vi.fn((id: string) => (id === "p1" ? mockProject : undefined)),
    create: vi.fn((data: Partial<typeof mockProject>) => ({ ...mockProject, ...data })),
    update: vi.fn((_id: string, patch: Partial<typeof mockProject>) => ({ ...mockProject, ...patch })),
    delete: vi.fn(),
  } as unknown as import("../core/project-manager.js").ProjectManager;

  const fsDeps = {
    existsSync: vi.fn(() => true),
    mkdirSync: vi.fn(),
    writeFileSync: vi.fn(),
  };

  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createProjectRoutes(projectManager, fsDeps));
  return { app, projectManager, fsDeps };
}

describe("Project Routes (Plan D'' simplified)", () => {
  it("GET /api/projects returns 200 with array", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects");
    expect(res.status).toBe(200);
    const body = (await res.json()) as { data: unknown[] };
    expect(body.data).toHaveLength(1);
  });

  it("GET /api/projects/:id returns 200 when known", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1");
    expect(res.status).toBe(200);
  });

  it("GET /api/projects/:id returns 404 when unknown", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/missing");
    expect(res.status).toBe(404);
  });

  it("POST /api/projects with valid body returns 201", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New", path: "/tmp/new" }),
    });
    expect(res.status).toBe(201);
  });

  it("POST /api/projects missing name returns 400", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: "/tmp" }),
    });
    expect(res.status).toBe(400);
  });

  it("PATCH /api/projects/:id returns 200 for known id", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Renamed" }),
    });
    expect(res.status).toBe(200);
  });

  it("DELETE /api/projects/:id returns 200", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1", { method: "DELETE" });
    expect(res.status).toBe(200);
  });

  // Iterate 3.7e-b3 (2026-04-22) — PATCH body flows through project-manager
  // update() which merges settings. This route-level test only asserts the
  // body is forwarded intact; the merge semantics are covered by the
  // project-manager unit tests separately.
  it("PATCH /api/projects/:id forwards settings.color to projectManager.update", async () => {
    const { app, projectManager } = setup();
    const res = await app.request("/api/projects/p1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: { color: "#B8A590" } }),
    });
    expect(res.status).toBe(200);
    expect(projectManager.update).toHaveBeenCalledWith("p1", {
      settings: { color: "#B8A590" },
    });
  });

  // Iterate 3.7e-b3 (2026-04-22) — root-cause test for the "Create Project
  // erstellt nichts" UAT regression. When the route throws a 500 (e.g.
  // mkdirSync fails on Windows EACCES), the client must see a JSON error
  // body so ProjectWizard can render the inline banner.
  it("POST /api/projects surfaces mkdirSync failures as 500 with JSON error body", async () => {
    const { app, fsDeps } = setup();
    fsDeps.existsSync.mockReturnValue(false);
    fsDeps.mkdirSync.mockImplementation(() => {
      const err = new Error("EACCES: permission denied, mkdir 'C:\\forbidden'");
      throw err;
    });
    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New", path: "C:/forbidden" }),
    });
    expect(res.status).toBe(500);
    const body = (await res.json()) as { error: string };
    // The generic error handler returns {error: "Internal server error"} —
    // the important contract for the UI is just that a JSON body exists so
    // ProjectWizard's inline error banner has something non-empty to show.
    expect(typeof body.error).toBe("string");
    expect(body.error.length).toBeGreaterThan(0);
  });
});
