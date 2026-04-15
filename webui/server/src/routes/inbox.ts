import { Hono } from "hono";
import type { InboxManager } from "../core/inbox-manager.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { TaskManager } from "../core/task-manager.js";
import type { ProjectManager } from "../core/project-manager.js";
import type { ProcessGovernor } from "../core/process-governor.js";
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
  // governor was iterate 11.1's zombie-check dep. Iterate 11.2 removed
  // the check (was too aggressive, hid legit items after server restart)
  // so the parameter is kept for backwards-compat of the 5-arg signature
  // but no longer used. Iterate 12 will implement task_orphaned events
  // at the event-store level, obsoleting any route-level zombie logic.
  _governor?: ProcessGovernor,
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
    const taskActive = all.filter((item: InboxItem) => {
      const task = taskManager.getTaskById(item.projectId, item.taskId);
      return task !== undefined && isActive(task.status);
    });

    // Iterate 13.2 — "latest pending per task" (newest createdAt wins).
    // Revert of 11.3: because Claude CLI in `-p` stream-json mode does NOT
    // block on AskUserQuestion (see ADR-023), the oldest pending question
    // is typically STALE — Claude has already moved past it with a default
    // decision. The newest pending question is the only one still
    // meaningfully answerable. Strict `>` keeps the earlier insertion on
    // ties, so same-turn duplicates still collapse deterministically.
    const answered = taskActive.filter((i) => i.status === "answered");
    const pendingByTask = new Map<string, InboxItem>();
    for (const item of taskActive) {
      if (item.status !== "pending") continue;
      const existing = pendingByTask.get(item.taskId);
      if (!existing || item.createdAt > existing.createdAt) {
        pendingByTask.set(item.taskId, item);
      }
    }
    const visible = [...pendingByTask.values(), ...answered];

    return c.json({ data: visible });
  });

  app.post("/api/inbox/:id/answer", async (c) => {
    const body = await c.req.json();
    // Iterate 14.2 — body shape:
    //   { answers: [{ index: 0, answer: "..." }, { index: 1, answer: "..." }] }
    // Back-compat for a flat `{ answer: "..." }` body: maps to the sole
    // part (index 0) — only valid when the item has a single part.
    let answers: Array<{ index: number; answer: string }>;
    if (Array.isArray(body.answers)) {
      answers = body.answers.map((a: unknown) => {
        if (!a || typeof a !== "object") {
          throw new AppError("answers entries must be objects", 400);
        }
        const entry = a as { index?: unknown; answer?: unknown };
        if (typeof entry.index !== "number" || typeof entry.answer !== "string") {
          throw new AppError("each answer needs { index: number, answer: string }", 400);
        }
        return { index: entry.index, answer: entry.answer };
      });
    } else if (typeof body.answer === "string") {
      answers = [{ index: 0, answer: body.answer }];
    } else {
      throw new AppError("answers array or legacy answer string is required", 400);
    }

    const item = await inboxManager.answer(c.req.param("id"), answers);
    sseManager.broadcast({
      type: "inbox:answered",
      payload: { id: item.id, projectId: item.projectId },
      timestamp: new Date().toISOString(),
    });
    return c.json({ data: item });
  });

  return app;
}
