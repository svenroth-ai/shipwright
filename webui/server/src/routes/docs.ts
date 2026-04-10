import { Hono } from "hono";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";
import { buildFileTree, readFileContent } from "../bridge/doc-index.js";

export function createDocsRoutes(projectManager: ProjectManager): Hono {
  const app = new Hono();

  app.get("/api/projects/:id/docs", async (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);

    const file = c.req.query("file");
    if (file) {
      const content = await readFileContent(file, project.path);
      return c.json({ data: { content, path: file } });
    }

    const tree = buildFileTree(project.path);
    return c.json({ data: tree });
  });

  return app;
}
