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

  // ---- Iterate 14.4 — POST /api/projects/pipeline ----
  describe("POST /api/projects/pipeline", () => {
    function pipelineSetup(overrides: {
      existingPaths?: string[];
      hasRunConfig?: boolean;
      pathIsDir?: boolean;
      pathExists?: boolean;
      profileExists?: boolean;
      spawnFails?: boolean;
    } = {}) {
      const projectManager = {
        getAll: vi.fn(() => (overrides.existingPaths ?? []).map((p, i) => ({
          id: `existing-${i}`, name: "Existing", path: p, profile: "default",
          status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01",
        }))),
        getById: vi.fn(() => undefined),
        create: vi.fn((data: any) => ({ id: "new-id", ...data, createdAt: "2026-01-01", lastActive: "2026-01-01" })),
      } as any;
      const fileWatcher = { watchProject: vi.fn(), unwatchProject: vi.fn() } as any;
      const eventStore = {} as any;
      const sseManager = { broadcast: vi.fn() } as any;
      const fsDeps = {
        existsSync: vi.fn((p: string) => {
          if (p.endsWith("shipwright_run_config.json")) return overrides.hasRunConfig === true;
          if (p.endsWith(".shipwright-webui")) return false;
          return overrides.pathExists !== false;
        }),
        mkdirSync: vi.fn(),
        writeFileSync: vi.fn(),
        statSync: vi.fn(() => ({ isDirectory: () => overrides.pathIsDir !== false })),
        loadProfile: vi.fn(() => overrides.profileExists !== false ? { name: "supabase-nextjs" } : null),
        profilesDir: "/fake",
        spawnInitialProjectPhase: vi.fn(async () => {
          if (overrides.spawnFails) throw new Error("spawn failed");
          return { taskId: "task-new" };
        }),
      };

      const app = new Hono();
      app.onError(errorHandler);
      app.route("/", createProjectRoutes(projectManager, fileWatcher, eventStore, sseManager, fsDeps));
      return { app, fsDeps, projectManager };
    }

    it("returns 202 on success and writes run_config + spawns task", async () => {
      const { app, fsDeps } = pipelineSetup();
      const res = await app.request("/api/projects/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "My App", path: "/tmp/my-app", profile: "supabase-nextjs" }),
      });
      expect(res.status).toBe(202);
      const body = await res.json();
      expect(body.data.projectId).toBe("new-id");
      expect(body.data.taskId).toBe("task-new");
      expect(fsDeps.writeFileSync).toHaveBeenCalled();
      expect(fsDeps.spawnInitialProjectPhase).toHaveBeenCalled();
      // Check run_config content
      const writeCall = fsDeps.writeFileSync.mock.calls.find(([p]: any[]) =>
        p.endsWith("shipwright_run_config.json"));
      const written = JSON.parse(writeCall![1] as string);
      expect(written.profile).toBe("supabase-nextjs");
      expect(written.status).toBe("pending");
      expect(written.standalone).toBe(false);
      expect(written.pipeline).toContain("project");
    });

    it("rejects path traversal '..' segments with 400", async () => {
      const { app } = pipelineSetup();
      const res = await app.request("/api/projects/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "X", path: "/tmp/../etc", profile: "supabase-nextjs" }),
      });
      expect(res.status).toBe(400);
    });

    it("returns 400 when target directory does not exist", async () => {
      const { app } = pipelineSetup({ pathIsDir: false });
      const res = await app.request("/api/projects/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "X", path: "/tmp/missing", profile: "supabase-nextjs" }),
      });
      expect(res.status).toBe(400);
    });

    it("returns 409 when path is already registered", async () => {
      const { app } = pipelineSetup({ existingPaths: ["/tmp/dup"] });
      const res = await app.request("/api/projects/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "X", path: "/tmp/dup", profile: "supabase-nextjs" }),
      });
      expect(res.status).toBe(409);
    });

    it("returns 409 when run_config already exists at target", async () => {
      const { app } = pipelineSetup({ hasRunConfig: true });
      const res = await app.request("/api/projects/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "X", path: "/tmp/has-config", profile: "supabase-nextjs" }),
      });
      expect(res.status).toBe(409);
    });

    it("returns 400 when profile cannot be loaded", async () => {
      const { app } = pipelineSetup({ profileExists: false });
      const res = await app.request("/api/projects/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "X", path: "/tmp/x", profile: "nope" }),
      });
      expect(res.status).toBe(400);
    });
  });

  it("POST /api/projects initializes project directory but does NOT write run_config (iterate 14.9)", async () => {
    // Iterate 14.9 / Bug C — POST /api/projects is the generic registry
    // endpoint and must NOT auto-write shipwright_run_config.json, because
    // that forced every registered directory into "pipeline" mode and
    // broke the Standalone affordance. Pipeline projects use the dedicated
    // POST /api/projects/pipeline endpoint which writes run_config itself.
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
    // Directories (project dir + .shipwright-webui) were created
    expect(fsDeps.mkdirSync).toHaveBeenCalled();
    // run_config.json must NOT have been written — that would flip the
    // project to "pipeline" mode and break the Standalone badge/hint.
    const writeCalls = fsDeps.writeFileSync.mock.calls.filter(
      ([path]: [string]) => typeof path === "string" && path.includes("shipwright_run_config.json"),
    );
    expect(writeCalls).toHaveLength(0);
    // File watcher was started for the new project
    expect(fileWatcher.watchProject).toHaveBeenCalled();
  });
});
