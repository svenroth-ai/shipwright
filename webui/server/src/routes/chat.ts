import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { ChatStore } from "../core/chat-store.js";
import type { ProcessGovernor } from "../core/process-governor.js";
import type { ClaudeAdapter, UserContentBlock } from "../core/claude-adapter.js";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";

interface ChatImagePayload {
  media_type: string;
  data: string; // base64
}

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
    const body = await c.req.json() as {
      taskId?: string;
      message?: string;
      images?: ChatImagePayload[];
    };
    if (!body.taskId || (!body.message && !body.images?.length)) {
      throw new AppError("taskId and message (or images) are required", 400);
    }

    const taskId = body.taskId;

    // 1. Persist the user message immediately so it shows in the UI
    const userChatMessage = {
      id: randomUUID(),
      taskId,
      type: "user" as const,
      content: body.message ?? "",
      ...(body.images && body.images.length > 0 ? { images: body.images } : {}),
      timestamp: new Date().toISOString(),
    };
    await chatStore.append(project.path, taskId, userChatMessage);

    // 2. Find the running Claude process for this task
    const proc = governor.getProcess(taskId);
    if (!proc || proc.state === "exited") {
      throw new AppError(
        "Task is not running. Start the task first using the Start button on the board.",
        400
      );
    }

    // 3. Build the content payload: string for plain text, or an array of
    //    text + image content blocks for multimodal messages.
    let content: string | UserContentBlock[];
    if (body.images && body.images.length > 0) {
      const blocks: UserContentBlock[] = [];
      if (body.message) {
        blocks.push({ type: "text", text: body.message });
      }
      for (const img of body.images) {
        blocks.push({
          type: "image",
          source: { type: "base64", media_type: img.media_type, data: img.data },
        });
      }
      content = blocks;
    } else {
      content = body.message ?? "";
    }

    // 4. Send it to the persistent CLI process via NDJSON stdin
    try {
      adapter.sendUserMessage(proc, content);
    } catch (err) {
      throw new AppError(`Failed to send message: ${String(err)}`, 500);
    }

    return c.json({ data: userChatMessage });
  });

  return app;
}
