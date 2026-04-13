import { Hono } from "hono";
import type { InboxManager } from "../core/inbox-manager.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { TaskManager } from "../core/task-manager.js";
import type { ProjectManager } from "../core/project-manager.js";
import type { InboxStatus, InboxItem } from "../../../client/src/types/inbox.js";
import type { TaskStatus } from "../../../client/src/types/task.js";
import { AppError } from "../middleware/error-handler.js";

/** Task statuses that make an inbox item pointless to surface in the UI —
 *  the Claude process is gone and the user can't answer anything. Iterate 11
 *  filter to stop the inbox from showing ghost items for completed/
 *  cancelled/failed tasks. */
const TERMINAL_TASK_STATUS: readonly TaskStatus[] = [
  "done",
  "failed",
  "cancelled",
  "orphaned",
] as const;

function isActive(status: TaskStatus | undefined): boolean {
  if (!status) return false;
  return !(TERMINAL_TASK_STATUS as readonly string[]).includes(status);
}

export function createInboxRoutes(
  inboxManager: InboxManager,
  sseManager: SSEManager,
  taskManager?: TaskManager,
  projectManager?: ProjectManager,
): Hono {
  const app = new Hono();

  app.get("/api/inbox", (c) => {
    const status = c.req.query("status") as InboxStatus | undefined;
    const filter = status ? { status } : undefined;
    const all = inboxManager.getAll(filter);

    // Iterate 11 — drop inbox items whose owning task is terminal or
    // doesn't exist anymore. Without this the inbox shows ghost items
    // for tasks the user deleted/closed, and iterate-9's chat-history
    // replay resurrects them on every restart.
    if (!taskManager || !projectManager) {
      return c.json({ data: all });
    }
    const active = all.filter((item: InboxItem) => {
      const task = taskManager.getTaskById(item.projectId, item.taskId);
      return task !== undefined && isActive(task.status);
    });
    return c.json({ data: active });
  });

  app.post("/api/inbox/:id/answer", async (c) => {
    const body = await c.req.json();
    if (!body.answer) throw new AppError("answer is required", 400);
    const item = await inboxManager.answer(c.req.param("id"), body.answer);
    sseManager.broadcast({
      type: "inbox:answered",
      payload: { id: item.id, projectId: item.projectId },
      timestamp: new Date().toISOString(),
    });
    return c.json({ data: item });
  });

  return app;
}
