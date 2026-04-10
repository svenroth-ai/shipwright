import { Hono } from "hono";
import { cors } from "hono/cors";
import { serveStatic } from "@hono/node-server/serve-static";
import { serve } from "@hono/node-server";
import { spawn } from "child_process";
import fs from "fs";
import { readFile, writeFile, appendFile } from "fs/promises";
import * as lockfile from "proper-lockfile";
import cron from "node-cron";
import chokidar from "chokidar";

import { getConfig } from "./config.js";
import { errorHandler } from "./middleware/error-handler.js";
import { requestLogger } from "./middleware/logger.js";
import { EventStore } from "./core/event-store.js";
import { SSEManager } from "./core/sse-manager.js";
import { ClaudeAdapter } from "./core/claude-adapter.js";
import { isAskUserQuestion } from "./core/ndjson-parser.js";
import { ProcessGovernor } from "./core/process-governor.js";
import { HeartbeatScheduler } from "./core/heartbeat.js";
import { ProjectManager } from "./core/project-manager.js";
import { TaskManager } from "./core/task-manager.js";
import { InboxManager } from "./core/inbox-manager.js";
import { ChatStore } from "./core/chat-store.js";
import { FileWatcher } from "./core/file-watcher.js";
import { readEventsFromFile } from "./bridge/event-reader.js";
import { emitTaskCreatedEvent } from "./bridge/event-writer.js";

import { createProjectRoutes } from "./routes/projects.js";
import { createTaskRoutes } from "./routes/tasks.js";
import { createInboxRoutes } from "./routes/inbox.js";
import { createChatRoutes } from "./routes/chat.js";
import { createPipelineRoutes } from "./routes/pipeline.js";
import { createDocsRoutes } from "./routes/docs.js";
import { createClassifyRoutes } from "./routes/classify.js";
import { createSettingsRoutes } from "./routes/settings.js";
import { createSSERoute } from "./routes/sse.js";

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

// Initialize managers (when running as server, not during import for tests)
const isMainModule =
  typeof process !== "undefined" &&
  process.argv[1] &&
  (process.argv[1].endsWith("index.ts") ||
    process.argv[1].endsWith("index.js"));

if (isMainModule) {
  void (async () => {
    // 1. Core stores
    const eventStore = new EventStore();
    const sseManager = new SSEManager();

    // 2. Chat store
    const chatStoreDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      appendFile: (p: string, d: string) => appendFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
    };
    const chatStore = new ChatStore(chatStoreDeps);

    // 3. Claude adapter with event forwarding
    const adapter = new ClaudeAdapter({ spawn }, (taskId, msg) => {
      // Forward to SSE
      sseManager.broadcast({
        type: "chat:message",
        payload: { taskId, message: msg },
        timestamp: new Date().toISOString(),
      });

      // Check for AskUserQuestion
      if (isAskUserQuestion(msg)) {
        const input = msg.tool_input as { question?: string; context?: string; options?: string[] } | undefined;
        inboxManager.addQuestion(
          "", // projectId resolved by task lookup
          taskId,
          input?.question ?? "Question from Claude",
          input?.context,
          input?.options
        );
      }
    });

    // 4. Process governor
    const governorDeps = {
      isProcessRunning: (pid: number) => { try { process.kill(pid, 0); return true; } catch { return false; } },
      kill: (pid: number, signal?: string) => process.kill(pid, signal as NodeJS.Signals),
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
    };
    const governor = new ProcessGovernor(
      config.maxConcurrent,
      adapter,
      governorDeps,
      `${config.registryDir}/pids.json`
    );

    // 5. Heartbeat
    const heartbeat = new HeartbeatScheduler(governor, governorDeps, { schedule: cron.schedule });

    // 6. Project manager
    const projectManagerDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
      readdirSync: (p: string, o?: { withFileTypes: boolean }) => fs.readdirSync(p, o as any) as any,
    };
    const projectManager = new ProjectManager(`${config.registryDir}/projects.json`, projectManagerDeps);
    await projectManager.load();

    // 7. Task manager
    const taskManager = new TaskManager(eventStore);

    // 8. Inbox manager
    const inboxManager = new InboxManager(governor, adapter, (item) => {
      sseManager.broadcast({
        type: "inbox:new",
        payload: item,
        timestamp: new Date().toISOString(),
      });
    });

    // 9. File watcher
    const fileWatcher = new FileWatcher({ watch: chokidar.watch });

    // 10. Event writer deps
    const writerDeps = {
      appendFile: (p: string, d: string) => appendFile(p, d),
      lock: async (p: string) => {
        const release = await lockfile.lock(p, { retries: 3 });
        return release;
      },
    };

    // Replay events for each project
    const fsDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      existsSync: (p: string) => fs.existsSync(p),
    };

    for (const project of projectManager.getAll()) {
      const eventsPath = `${project.path}/shipwright_events.jsonl`;
      const events = await readEventsFromFile(eventsPath, fsDeps);
      eventStore.replayProject(project.id, events);

      fileWatcher.watchProject(project.id, project.path, (type, _path) => {
        if (type === "event") {
          // Re-read events — simplified, full implementation would diff
          sseManager.broadcast({
            type: "task:updated",
            payload: { projectId: project.id },
            timestamp: new Date().toISOString(),
          });
        } else {
          sseManager.broadcast({
            type: "pipeline:updated",
            payload: { projectId: project.id },
            timestamp: new Date().toISOString(),
          });
        }
      });
    }

    // Cleanup orphans and start heartbeat
    await governor.cleanupOrphans();
    heartbeat.start();

    // Settings deps
    const settingsDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
    };

    // Mount routes
    app.route("/", createProjectRoutes(projectManager, fileWatcher, eventStore, sseManager));
    app.route("/", createTaskRoutes({
      taskManager,
      eventStore,
      governor,
      adapter,
      sseManager,
      projectManager,
      emitTaskCreatedEvent: (fp, tid, pid, desc, intent, priority) =>
        emitTaskCreatedEvent(fp, tid, pid, desc, intent, priority, writerDeps),
    }));
    app.route("/", createInboxRoutes(inboxManager, sseManager));
    app.route("/", createChatRoutes(chatStore, governor, adapter, projectManager));
    app.route("/", createPipelineRoutes(eventStore, projectManager));
    app.route("/", createDocsRoutes(projectManager));
    app.route("/", createClassifyRoutes(projectManager));
    app.route("/", createSettingsRoutes(`${config.registryDir}/settings.json`, settingsDeps));
    app.route("/", createSSERoute(sseManager));

    // Graceful shutdown
    const shutdown = async () => {
      console.log("Shutting down...");
      heartbeat.stop();
      fileWatcher.unwatchAll();
      sseManager.closeAll();
      for (const proc of governor.getAllActive()) {
        adapter.terminate(proc);
      }
      await governor.persistPids();
      process.exit(0);
    };
    process.on("SIGTERM", shutdown);
    process.on("SIGINT", shutdown);

    // Start server
    serve({ fetch: app.fetch, port: config.port }, (info) => {
      console.log(`Shipwright Command Center listening on http://localhost:${info.port}`);
    });
  })();
}

// Static file serving (after API routes when running as main, but always registered for tests)
app.use("/*", serveStatic({ root: config.staticDir }));

// 404 handler
app.notFound((c) => {
  return c.json({ error: "Not found" }, 404);
});
