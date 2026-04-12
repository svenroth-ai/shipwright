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
import { isAskUserQuestion, extractContentBlocks } from "./core/ndjson-parser.js";
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
  void (async () => { try {
    // Safety net: never crash the server on unhandled errors
    process.on("uncaughtException", (err) => {
      console.error(JSON.stringify({ level: "error", message: "Uncaught exception (server stays alive)", error: String(err), stack: err.stack }));
    });
    process.on("unhandledRejection", (reason) => {
      console.error(JSON.stringify({ level: "error", message: "Unhandled rejection (server stays alive)", error: String(reason) }));
    });


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

    // 3. Claude adapter with event forwarding + chat persistence
    const adapter = new ClaudeAdapter({ spawn }, (taskId, msg) => {
      // Find project for this task (needed for SSE payload and persistence)
      let projectId: string | undefined;
      let projectPath: string | undefined;
      const allProjects = projectManager.getAll();
      for (const proj of allProjects) {
        const task = taskManager.getTaskById(proj.id, taskId);
        if (task) {
          projectId = proj.id;
          projectPath = proj.path;
          break;
        }
      }

      // Forward raw NDJSON to SSE for real-time streaming
      sseManager.broadcast({
        type: "chat:message",
        payload: { taskId, projectId, message: msg },
        timestamp: new Date().toISOString(),
      });

      // Extract structured ChatMessages and persist ALL types
      const chatMessages = extractContentBlocks(taskId, msg);
      if (chatMessages.length > 0 && projectPath) {
        for (const chatMsg of chatMessages) {
          chatStore.append(projectPath, taskId, chatMsg)
            .catch((err) => console.error(JSON.stringify({ level: "error", message: "Chat persist error", error: String(err) })));
        }
      }

      // Check for AskUserQuestion
      if (isAskUserQuestion(msg)) {
        const input = msg.tool_input as { question?: string; context?: string; options?: string[] } | undefined;
        inboxManager.addQuestion(
          "", // projectId resolved by task lookup
          taskId,
          input?.question ?? "Question from Claude",
          input?.context,
          input?.options
        ).catch((err) => console.error(JSON.stringify({ level: "error", message: "Inbox persist error", error: String(err) })));
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

    // 5. Heartbeat — notifies frontend when dead process detected
    const heartbeat = new HeartbeatScheduler(governor, governorDeps, { schedule: cron.schedule }, {
      onDeadProcess: (taskId, projectId) => {
        sseManager.broadcast({
          type: "task:updated",
          payload: { taskId, projectId },
          timestamp: new Date().toISOString(),
        });
      },
    });

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
    const inboxStoreDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      appendFile: (p: string, d: string) => appendFile(p, d),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
    };
    const inboxManager = new InboxManager(governor, adapter, (item) => {
      sseManager.broadcast({
        type: "inbox:new",
        payload: item,
        timestamp: new Date().toISOString(),
      });
    }, inboxStoreDeps);

    // 9. File watcher
    const fileWatcher = new FileWatcher({ watch: chokidar.watch });

    // 10. Event writer deps
    const writerDeps = {
      appendFile: (p: string, d: string) => appendFile(p, d),
      lock: async (p: string) => {
        const release = await lockfile.lock(p, { retries: 3 });
        return release;
      },
      ensureDir: (p: string) => { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); },
      ensureFile: (p: string) => { if (!fs.existsSync(p)) fs.writeFileSync(p, ""); },
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

      await inboxManager.loadFromDisk(project.id, project.path);


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
    const orphanResult = await governor.cleanupOrphans();
    console.log("[boot] Orphan cleanup:", orphanResult);
    heartbeat.start();

    // Settings deps
    const settingsDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
    };

    // Mount routes
    const projectFsDeps = {
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
      writeFileSync: (p: string, d: string) => fs.writeFileSync(p, d),
    };
    app.route("/", createProjectRoutes(projectManager, fileWatcher, eventStore, sseManager, projectFsDeps));
    const settingsPath = `${config.registryDir}/settings.json`;
    app.route("/", createTaskRoutes({
      taskManager,
      eventStore,
      governor,
      adapter,
      sseManager,
      projectManager,
      emitTaskCreatedEvent: (fp, tid, pid, desc, intent, priority) =>
        emitTaskCreatedEvent(fp, tid, pid, desc, intent, priority, writerDeps),
      readGlobalSettings: async () => {
        if (!fs.existsSync(settingsPath)) return {};
        try {
          const content = await readFile(settingsPath, "utf-8");
          return JSON.parse(content);
        } catch {
          return {};
        }
      },
    }));
    app.route("/", createInboxRoutes(inboxManager, sseManager));
    app.route("/", createChatRoutes(chatStore, governor, adapter, projectManager));
    app.route("/", createPipelineRoutes(eventStore, projectManager));
    app.route("/", createDocsRoutes(projectManager));
    app.route("/", createClassifyRoutes(projectManager));
    app.route("/", createSettingsRoutes(settingsPath, settingsDeps));
    app.route("/", createSSERoute(sseManager));

    // Graceful shutdown with timeout
    const shutdown = async () => {
      console.log("Shutting down...");
      // Force exit after 5s if processes don't terminate
      const forceTimer = setTimeout(() => {
        console.error("Shutdown timeout — force exiting");
        process.exit(1);
      }, 5000);
      forceTimer.unref();

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
  } catch (err) {
    console.error("FATAL: Server startup failed:", err);
    process.exit(1);
  }
  })();
}

// Static file serving (after API routes when running as main, but always registered for tests)
app.use("/*", serveStatic({ root: config.staticDir }));

// 404 handler
app.notFound((c) => {
  return c.json({ error: "Not found" }, 404);
});
