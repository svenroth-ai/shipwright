import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { ChatStore } from "../core/chat-store.js";
import type { ProcessGovernor } from "../core/process-governor.js";
import type { ClaudeAdapter } from "../core/claude-adapter.js";
import type { ProjectManager } from "../core/project-manager.js";
import type { TaskManager } from "../core/task-manager.js";
import type { EventStore } from "../core/event-store.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { SessionRegistry } from "../core/session-registry.js";
import { AppError } from "../middleware/error-handler.js";

export function createChatRoutes(
  chatStore: ChatStore,
  governor: ProcessGovernor,
  adapter: ClaudeAdapter,
  projectManager: ProjectManager,
  taskManager?: TaskManager,
  eventStore?: EventStore,
  sseManager?: SSEManager,
  sessionRegistry?: SessionRegistry
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

    const taskId = body.taskId as string;

    // 1. Persist the user message immediately so it shows in the UI
    const userChatMessage = {
      id: randomUUID(),
      taskId,
      type: "user" as const,
      content: body.message as string,
      timestamp: new Date().toISOString(),
    };
    await chatStore.append(project.path, taskId, userChatMessage);

    // 2. Resolve the REAL Claude session_id via the SessionRegistry.
    //    Claude CLI emits its own session_id in the system/init event — we
    //    capture it there (index.ts onEvent) and store it per task here.
    //    --resume requires THIS id, not the UUID we supplied to --session-id.
    const realSessionId = sessionRegistry?.get(taskId);
    if (!realSessionId) {
      throw new AppError("No Claude session recorded for this task yet. Wait for the initial response before sending follow-ups.", 409);
    }

    // 3. Spawn a new Claude process with --resume + the user message as prompt.
    //    In print mode Claude exits after responding, so we need a fresh spawn
    //    for each message. The existing process (if any) is already exited.
    const existing = governor.getProcess(taskId);
    if (existing && existing.state !== "exited") {
      // Race: another message is still being processed. Reject.
      throw new AppError("Another message is still being processed", 409);
    }

    try {
      const result = await governor.acquire({
        projectDir: project.path,
        projectId: project.id,
        taskId,
        sessionId: realSessionId,
        resume: "explicit",
        pluginDirs: project.settings?.claudePluginDirs ?? [],
        prompt: body.message as string,
      });

      if (result === "queued") {
        return c.json({ data: userChatMessage, queued: true }, 202);
      }

      // Mark task as running again for the follow-up
      if (eventStore) {
        eventStore.addEvent(project.id, {
          type: "phase_started",
          timestamp: new Date().toISOString(),
          task_id: taskId,
          project_id: project.id,
          phase: "build",
        });
      }
      if (sseManager) {
        sseManager.broadcast({
          type: "task:updated",
          payload: { taskId, projectId: project.id },
          timestamp: new Date().toISOString(),
        });
      }

      return c.json({ data: userChatMessage });
    } catch (err) {
      throw new AppError(`Failed to spawn Claude: ${String(err)}`, 500);
    }
  });

  return app;
}
