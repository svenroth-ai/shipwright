/*
 * /api/projects/* — minimal CRUD. Plan D'' Sub-iterate 3 simplification:
 * no more fileWatcher + eventStore + sseManager side-effects (all removed
 * with the chat/pipeline runtime).
 *
 * The wizard's "pipeline" project endpoint and initial-phase spawning are
 * gone — projects are plain metadata registrations. Pipeline mode is a
 * follow-up iterate once external-launch ships.
 */

import { Hono } from "hono";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";

export interface ProjectRouteDeps {
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
  writeFileSync: (path: string, data: string) => void;
}

export function createProjectRoutes(
  projectManager: ProjectManager,
  fsDeps?: ProjectRouteDeps,
): Hono {
  const app = new Hono();

  app.get("/api/projects", (c) => c.json({ data: projectManager.getAll() }));

  app.get("/api/projects/:id", (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    return c.json({ data: project });
  });

  app.post("/api/projects", async (c) => {
    const body = await c.req.json();
    if (!body.name || !body.path) {
      throw new AppError("name and path are required", 400);
    }
    if (fsDeps) {
      if (!fsDeps.existsSync(body.path)) {
        fsDeps.mkdirSync(body.path, { recursive: true });
      }
      const webuiDir = `${body.path}/.shipwright-webui`;
      if (!fsDeps.existsSync(webuiDir)) {
        fsDeps.mkdirSync(webuiDir, { recursive: true });
      }
    }
    const project = projectManager.create(body);
    return c.json({ data: project }, 201);
  });

  app.patch("/api/projects/:id", async (c) => {
    const body = await c.req.json();
    const updated = projectManager.update(c.req.param("id"), body);
    if (!updated) throw new AppError("Project not found", 404);
    return c.json({ data: updated });
  });

  app.delete("/api/projects/:id", (c) => {
    projectManager.delete(c.req.param("id"));
    return c.json({ ok: true });
  });

  return app;
}
