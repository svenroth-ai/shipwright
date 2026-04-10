import { Hono } from "hono";
import { cors } from "hono/cors";
import { serveStatic } from "@hono/node-server/serve-static";
import { serve } from "@hono/node-server";
import { getConfig } from "./config.js";
import { errorHandler, AppError } from "./middleware/error-handler.js";
import { requestLogger } from "./middleware/logger.js";

const config = getConfig();
const startTime = Date.now();

export const app = new Hono();

// Middleware
app.use(
  "*",
  cors({
    origin: (origin) => {
      if (origin && origin.includes("localhost")) {
        return origin;
      }
      return null;
    },
  })
);
app.use("*", requestLogger);
app.onError(errorHandler);

// Health endpoint
app.get("/api/health", (c) => {
  return c.json({
    status: "ok",
    version: "0.1.0",
    uptime: Math.floor((Date.now() - startTime) / 1000),
  });
});

// Static file serving
app.use(
  "/*",
  serveStatic({
    root: config.staticDir,
  })
);

// 404 handler for unmatched routes
app.notFound((c) => {
  return c.json({ error: "Not found" }, 404);
});

// Start server (only when not imported for testing)
const isMainModule =
  typeof process !== "undefined" &&
  process.argv[1] &&
  (process.argv[1].endsWith("index.ts") ||
    process.argv[1].endsWith("index.js"));

if (isMainModule) {
  serve({ fetch: app.fetch, port: config.port }, (info) => {
    console.log(`Shipwright Command Center listening on http://localhost:${info.port}`);
  });
}
