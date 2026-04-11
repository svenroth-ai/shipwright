import { Hono } from "hono";
import type { InboxManager } from "../core/inbox-manager.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { InboxStatus } from "../../../client/src/types/inbox.js";
import { AppError } from "../middleware/error-handler.js";

export function createInboxRoutes(
  inboxManager: InboxManager,
  sseManager: SSEManager
): Hono {
  const app = new Hono();

  app.get("/api/inbox", (c) => {
    const status = c.req.query("status") as InboxStatus | undefined;
    const filter = status ? { status } : undefined;
    return c.json({ data: inboxManager.getAll(filter) });
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
