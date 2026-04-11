import { Hono } from "hono";
import type { ProjectManager } from "../core/project-manager.js";
import type { FileWatcher } from "../core/file-watcher.js";
import type { EventStore } from "../core/event-store.js";
import type { SSEManager } from "../core/sse-manager.js";
import { AppError } from "../middleware/error-handler.js";

export interface ProjectRouteDeps {
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  writeFileSync: (path: string, data: string) => void;
}

export function createProjectRoutes(
  projectManager: ProjectManager,
  fileWatcher: FileWatcher,
  eventStore: EventStore,
  sseManager: SSEManager,
  fsDeps?: ProjectRouteDeps
): Hono {
  const app = new Hono();

  app.get("/api/projects", (c) => {
    return c.json({ data: projectManager.getAll() });
  });

  app.post("/api/projects", async (c) => {
    const body = await c.req.json();
    if (!body.name || !body.path) {
      throw new AppError("name and path are required", 400);
    }

    // Initialize project directory with minimal config files
    if (fsDeps) {
      if (!fsDeps.existsSync(body.path)) {
        fsDeps.mkdirSync(body.path, { recursive: true });
      }
      const runConfig = `${body.path}/shipwright_run_config.json`;
      if (!fsDeps.existsSync(runConfig)) {
        fsDeps.writeFileSync(runConfig, JSON.stringify({
          scope: "full_app",
          profile: body.profile ?? "custom",
          autonomy: "guided",
          pipeline: ["project", "design", "plan", "build", "test", "changelog", "deploy"],
          status: "not_started",
          current_step: null,
          completed_steps: [],
          project_summary: { name: body.name, description: body.description ?? "" },
          updated_at: new Date().toISOString(),
        }, null, 2));
      }
      // Ensure .shipwright-webui dir exists for chat/inbox
      const webuiDir = `${body.path}/.shipwright-webui`;
      if (!fsDeps.existsSync(webuiDir)) {
        fsDeps.mkdirSync(webuiDir, { recursive: true });
      }
    }

    const project = projectManager.create(body);

    // Start watching the new project for events
    fileWatcher.watchProject(project.id, project.path, (type) => {
      if (type === "event") {
        sseManager.broadcast({ type: "task:updated", payload: { projectId: project.id }, timestamp: new Date().toISOString() });
      } else {
        sseManager.broadcast({ type: "pipeline:updated", payload: { projectId: project.id }, timestamp: new Date().toISOString() });
      }
    });

    sseManager.broadcast({ type: "project:updated", payload: { id: project.id }, timestamp: new Date().toISOString() });
    return c.json({ data: project }, 201);
  });

  app.get("/api/projects/:id", (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    return c.json({ data: project });
  });

  app.patch("/api/projects/:id", async (c) => {
    const body = await c.req.json();
    const project = projectManager.update(c.req.param("id"), body);
    return c.json({ data: project });
  });

  app.delete("/api/projects/:id", (c) => {
    const id = c.req.param("id");
    fileWatcher.unwatchProject(id);
    projectManager.delete(id);
    sseManager.broadcast({
      type: "project:updated",
      payload: { id, deleted: true },
      timestamp: new Date().toISOString(),
    });
    return c.body(null, 204);
  });

  return app;
}
