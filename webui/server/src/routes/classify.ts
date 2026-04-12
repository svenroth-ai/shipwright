import { Hono } from "hono";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";
import { classifyIntent, classifyComplexity, classifyPhase } from "../bridge/intent-classifier.js";

export function createClassifyRoutes(projectManager: ProjectManager): Hono {
  const app = new Hono();

  app.post("/api/projects/:id/classify", async (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const body = await c.req.json();
    if (!body.description) throw new AppError("description is required", 400);

    const [intentResult, complexityResult, phaseResult] = await Promise.all([
      classifyIntent(body.description, project.path),
      classifyComplexity(body.description, project.path),
      classifyPhase(body.description, project.path),
    ]);

    return c.json({
      data: {
        intent: intentResult.intent,
        complexity: complexityResult.complexity,
        affected_frs: intentResult.affected_frs,
        phase: phaseResult.phase,
        phase_confidence: phaseResult.confidence,
      },
    });
  });

  return app;
}
