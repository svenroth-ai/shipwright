import { Hono } from "hono";
import type { ProjectManager } from "../core/project-manager.js";
import type { FileWatcher } from "../core/file-watcher.js";
import type { EventStore } from "../core/event-store.js";
import type { SSEManager } from "../core/sse-manager.js";
import { AppError } from "../middleware/error-handler.js";

export function createProjectRoutes(
  projectManager: ProjectManager,
  fileWatcher: FileWatcher,
  eventStore: EventStore,
  sseManager: SSEManager
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
    const project = projectManager.create(body);
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
