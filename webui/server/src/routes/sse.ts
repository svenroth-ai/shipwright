import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { SSEManager } from "../core/sse-manager.js";

export function createSSERoute(sseManager: SSEManager): Hono {
  const app = new Hono();

  app.get("/api/events", (c) => {
    const stream = new ReadableStream({
      start(controller) {
        const clientId = randomUUID();
        sseManager.addClient(clientId, controller);

        const encoder = new TextEncoder();
        const connectedEvent = `event: connected\ndata: ${JSON.stringify({ timestamp: new Date().toISOString() })}\n\n`;
        controller.enqueue(encoder.encode(connectedEvent));

        // Cleanup on abort
        c.req.raw.signal.addEventListener("abort", () => {
          sseManager.removeClient(clientId);
        });
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  });

  return app;
}
