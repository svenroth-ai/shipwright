import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createProjectRoutes } from "./projects.js";
import { errorHandler } from "../middleware/error-handler.js";
import type { Project } from "../../../client/src/types/project.js";

const mockProject: Project = {
  id: "p1", name: "Test", path: "/tmp", profile: "default",
  status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01",
};

function setup() {
  const projectManager = {
    getAll: vi.fn(() => [mockProject]),
    getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined),
    create: vi.fn((data: any) => ({ ...mockProject, ...data })),
    update: vi.fn((id: string, patch: any) => ({ ...mockProject, ...patch })),
    delete: vi.fn(),
  } as any;
  const fileWatcher = { unwatchProject: vi.fn(), watchProject: vi.fn() } as any;
  const eventStore = {} as any;
  const sseManager = { broadcast: vi.fn() } as any;

  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createProjectRoutes(projectManager, fileWatcher, eventStore, sseManager));
  return { app, projectManager };
}

describe("Project Routes", () => {
  it("GET /api/projects returns 200 with array", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data).toHaveLength(1);
  });

  it("POST /api/projects with valid body returns 201", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New", path: "/tmp" }),
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

  it("PATCH /api/projects/:id returns 200", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Updated" }),
    });
    expect(res.status).toBe(200);
  });

  it("DELETE /api/projects/:id returns 204", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1", { method: "DELETE" });
    expect(res.status).toBe(204);
  });

  it("GET /api/projects/:id for non-existent returns 404", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/nonexistent");
    expect(res.status).toBe(404);
  });

  it("POST /api/projects initializes project directory with config files", async () => {
    const projectManager = {
      getAll: vi.fn(() => []),
      create: vi.fn((data: any) => ({ ...mockProject, ...data })),
    } as any;
    const fileWatcher = { unwatchProject: vi.fn(), watchProject: vi.fn() } as any;
    const eventStore = {} as any;
    const sseManager = { broadcast: vi.fn() } as any;
    const fsDeps = {
      existsSync: vi.fn(() => false),
      mkdirSync: vi.fn(),
      writeFileSync: vi.fn(),
    };

    const app = new Hono();
    app.onError(errorHandler);
    app.route("/", createProjectRoutes(projectManager, fileWatcher, eventStore, sseManager, fsDeps));

    const res = await app.request("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New App", path: "/tmp/new-app", profile: "supabase-nextjs" }),
    });
    expect(res.status).toBe(201);
    // Directory was created
    expect(fsDeps.mkdirSync).toHaveBeenCalled();
    // Run config was written
    expect(fsDeps.writeFileSync).toHaveBeenCalled();
    const writtenPath = fsDeps.writeFileSync.mock.calls[0][0];
    expect(writtenPath).toContain("shipwright_run_config.json");
    const writtenContent = JSON.parse(fsDeps.writeFileSync.mock.calls[0][1]);
    expect(writtenContent.profile).toBe("supabase-nextjs");
    expect(writtenContent.project_summary.name).toBe("New App");
    // File watcher was started for the new project
    expect(fileWatcher.watchProject).toHaveBeenCalled();
  });
});
