import { Hono } from "hono";
import type { EventStore } from "../core/event-store.js";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";
import { getPipelineState } from "../bridge/pipeline-state.js";

export function createPipelineRoutes(
  eventStore: EventStore,
  projectManager: ProjectManager
): Hono {
  const app = new Hono();

  app.get("/api/projects/:id/pipeline", async (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const state = await getPipelineState(project.id, eventStore, project.path);
    return c.json({ data: state });
  });

  return app;
}
