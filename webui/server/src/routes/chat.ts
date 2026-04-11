import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { ChatStore } from "../core/chat-store.js";
import type { ProcessGovernor } from "../core/process-governor.js";
import type { ClaudeAdapter } from "../core/claude-adapter.js";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";

export function createChatRoutes(
  chatStore: ChatStore,
  governor: ProcessGovernor,
  adapter: ClaudeAdapter,
  projectManager: ProjectManager
): Hono {
  const app = new Hono();

  app.get("/api/projects/:id/chat/:taskId", async (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const messages = await chatStore.load(project.path, c.req.param("taskId"));
    return c.json({ data: messages });
  });

  app.post("/api/projects/:id/chat", async (c) => {
    const project = projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const body = await c.req.json();
    if (!body.taskId || !body.message) {
      throw new AppError("taskId and message are required", 400);
    }

    const proc = governor.getProcess(body.taskId);
    if (!proc || proc.state === "exited") {
      throw new AppError("Process not running", 400);
    }

    adapter.sendStdin(proc, body.message);

    const chatMessage = {
      id: randomUUID(),
      taskId: body.taskId,
      type: "user" as const,
      content: body.message,
      timestamp: new Date().toISOString(),
      settings: {
        model: body.model,
        mode: body.mode,
        effort: body.effort,
        autonomy: body.autonomy,
      },
    };
    await chatStore.append(project.path, body.taskId, chatMessage);
    return c.json({ data: chatMessage });
  });

  return app;
}
