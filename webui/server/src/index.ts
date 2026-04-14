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
import { broadcastAndPersistChat } from "./core/chat-broadcast.js";
import { extractAskUserPayload } from "../../client/src/lib/askUserPayload.js";
import { ProcessGovernor } from "./core/process-governor.js";
import { HeartbeatScheduler } from "./core/heartbeat.js";
import { ProjectManager } from "./core/project-manager.js";
import { TaskManager } from "./core/task-manager.js";
import { InboxManager } from "./core/inbox-manager.js";
import { ChatStore } from "./core/chat-store.js";
import { findOrphanAskUserQuestions } from "./core/inbox-replay.js";
import { FileWatcher } from "./core/file-watcher.js";
import { readEventsFromFile } from "./bridge/event-reader.js";
import {
  emitTaskCreatedEvent,
  emitPhaseStartedEvent,
  emitTaskCancelledEvent,
  emitTaskUpdatedEvent,
  emitWorkCompletedEvent,
  emitWorkFailedEvent,
  emitTaskOrphanedEvent,
} from "./bridge/event-writer.js";

import { createProjectRoutes } from "./routes/projects.js";
import { createTaskRoutes } from "./routes/tasks.js";
import { createInboxRoutes } from "./routes/inbox.js";
import { createChatRoutes } from "./routes/chat.js";
import { createPipelineRoutes } from "./routes/pipeline.js";
import { createDocsRoutes } from "./routes/docs.js";
import { createClassifyRoutes } from "./routes/classify.js";
import { createSettingsRoutes } from "./routes/settings.js";
import { createCapabilitiesRoutes } from "./routes/capabilities.js";
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
    // Safety net: keep the server alive on runtime errors from request
    // handlers BUT exit cleanly on fatal startup errors so `tsx watch`
    // can re-spawn the process. EADDRINUSE is the big one — it fires
    // during the reload window where the old process is still releasing
    // port 3847, and if we swallow it the new process sits there running
    // but not actually bound, masking every subsequent file change. See
    // ADR-018 for the full story.
    const FATAL_ERROR_CODES = new Set(["EADDRINUSE", "EACCES", "EADDRNOTAVAIL"]);
    process.on("uncaughtException", (err) => {
      const code = (err as NodeJS.ErrnoException).code;
      if (code && FATAL_ERROR_CODES.has(code)) {
        console.error(JSON.stringify({ level: "fatal", message: `Fatal startup error (${code}) — exiting so tsx watch can retry`, error: String(err), code }));
        process.exit(1);
      }
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

    // Shared cross-process lock + file-exists guard. Reused by every
    // JSON/JSONL writer below (events, projects, pids, inbox, settings)
    // so all write sites behave identically and nobody can accidentally
    // forget to serialize. proper-lockfile requires the target file to
    // exist (lstat), hence ensureFileExists.
    const lockPath = async (p: string) => {
      const release = await lockfile.lock(p, { retries: 3 });
      return release;
    };
    const ensureFileExists = (p: string) => {
      if (!fs.existsSync(p)) fs.writeFileSync(p, "");
    };

    // Event writer deps — hoisted so adapter's onExit can use them
    const writerDeps = {
      appendFile: (p: string, d: string) => appendFile(p, d),
      lock: lockPath,
      ensureDir: (p: string) => { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); },
      ensureFile: ensureFileExists,
    };

    // 3. Claude adapter with event forwarding + chat persistence + lifecycle events
    const adapter = new ClaudeAdapter(
      { spawn },
      (taskId, msg) => {
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

        // Iterate 13: extract ChatMessages first, then broadcast each one
        // individually with the same stable id it gets persisted with.
        // See plan vast-mapping-petal.md.
        const chatMessages = extractContentBlocks(taskId, msg);
        broadcastAndPersistChat(
          { taskId, projectId, projectPath, msg, chatMessages },
          { sseManager, chatStore },
        );

        // Check for AskUserQuestion — iterate over the extracted tool_use
        // ChatMessages so we cover BOTH standalone tool_use NDJSON events
        // and assistant-wrapped content-block tool_use entries. Use the
        // chat message's toolUseId as the inbox item id so the client's
        // AskUserCard (which sees the same ChatMessage) can correlate with
        // the persisted inbox item even after a page refresh. See ADR-018.
        //
        // Iterate 9: pass the REAL projectId (resolved at the top of the
        // callback via `allProjects` + `getTaskById`). Previously we passed
        // an empty string here with a stale "resolved by task lookup" TODO —
        // there was no such resolver, so inbox.jsonl was never written
        // (persistItem bails on empty projectId) and grouping by project
        // silently broke. See iterate-2026-04-13-wiring-fixes spec.
        if (projectId) {
          for (const chatMsg of chatMessages) {
            if (chatMsg.type === "tool_use" && chatMsg.toolName === "AskUserQuestion") {
              const payload = extractAskUserPayload(chatMsg.toolInput);
              inboxManager.addQuestion(
                projectId,
                taskId,
                payload.question || "Question from Claude",
                payload.context,
                payload.options,
                chatMsg.toolUseId,
              ).catch((err) => console.error(JSON.stringify({ level: "error", message: "Inbox persist error", error: String(err) })));
            }
          }

          // Legacy path: standalone tool_use event with AskUserQuestion.
          // extractContentBlocks already covers this so the for-loop above
          // handles it too, but keep this guard for any historical NDJSON
          // shapes that don't flow through extractContentBlocks.
          if (isAskUserQuestion(msg) && chatMessages.length === 0) {
            const rawInput = msg.tool_input ?? (msg.message as { tool_input?: unknown } | undefined)?.tool_input;
            const payload = extractAskUserPayload(rawInput);
            inboxManager.addQuestion(
              projectId,
              taskId,
              payload.question || "Question from Claude",
              payload.context,
              payload.options,
            ).catch((err) => console.error(JSON.stringify({ level: "error", message: "Inbox persist error", error: String(err) })));
          }
        }
      },
      // onExit: in persistent-process mode, the CLI stays alive for the whole
      // task conversation. Exit here means either:
      //   - user intentionally terminated (SIGTERM → exitCode null): silent
      //   - CLI crashed (exitCode > 0): emit work_failed
      //   - normal exit code 0: shouldn't happen in persistent mode, treat as ok
      (taskId, projectId, exitCode) => {
        const proj = projectManager.getById(projectId);
        if (!proj) return;
        const eventsPath = `${proj.path}/shipwright_events.jsonl`;

        // Release from governor + notify
        governor.release(taskId).catch(() => {});
        sseManager.broadcast({
          type: "task:updated",
          payload: { taskId, projectId },
          timestamp: new Date().toISOString(),
        });

        // Intentional terminate (SIGTERM) or normal exit → no lifecycle event
        if (exitCode === null || exitCode === 0) return;

        // Abnormal exit → work_failed
        eventStore.addEvent(projectId, {
          type: "work_failed",
          timestamp: new Date().toISOString(),
          task_id: taskId,
          project_id: projectId,
          detail: `Claude CLI exited with code ${exitCode}`,
        });
        emitWorkFailedEvent(eventsPath, taskId, projectId, `Exit code ${exitCode}`, writerDeps)
          .catch((err) => console.error(JSON.stringify({ level: "error", message: "Lifecycle event write failed", error: String(err) })));
      }
    );

    // 4. Process governor
    const governorDeps = {
      isProcessRunning: (pid: number) => { try { process.kill(pid, 0); return true; } catch { return false; } },
      kill: (pid: number, signal?: string) => process.kill(pid, signal as NodeJS.Signals),
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
      lock: lockPath,
      ensureFile: ensureFileExists,
    };
    const governor = new ProcessGovernor(
      config.maxConcurrent,
      adapter,
      governorDeps,
      `${config.registryDir}/pids.json`
    );

    // 5. Heartbeat construction is deferred until after projectManager +
    // eventStore are ready (iterate 12.0b: the reconciler needs both to
    // emit `task_orphaned` events on dead-PID detection). The binding
    // itself is created here with `let` so the shutdown handler lower
    // down can still .stop() it.
    let heartbeat!: HeartbeatScheduler;

    // 6. Project manager
    const projectManagerDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
      readdirSync: (p: string, o?: { withFileTypes: boolean }) => fs.readdirSync(p, o as any) as any,
      lock: lockPath,
      ensureFile: ensureFileExists,
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
      lock: lockPath,
      ensureFile: ensureFileExists,
    };
    const inboxManager = new InboxManager(governor, adapter, (item) => {
      sseManager.broadcast({
        type: "inbox:new",
        payload: item,
        timestamp: new Date().toISOString(),
      });
    }, inboxStoreDeps, {
      // Iterate 7: persist the synthetic tool_result as a chat message so
      // the folded tool-card flips to "Done" after an AskUserQuestion is
      // answered. Also broadcasts to SSE so open clients see it live.
      appendChatMessage: async (projectDir, taskId, message) => {
        await chatStore.append(projectDir, taskId, message);
        const resolvedProjectId =
          projectManager.getAll().find((p) => p.path === projectDir)?.id ?? "";
        sseManager.broadcast({
          type: "chat:message",
          payload: { taskId, projectId: resolvedProjectId, message },
          timestamp: new Date().toISOString(),
        });
      },
    });

    // 9. File watcher
    const fileWatcher = new FileWatcher({ watch: chokidar.watch });

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

      // Iterate 9 — chat-history replay for inbox. Walks every
      // chat-history/*.jsonl for this project and reconstructs InboxItems
      // for any tool_use AskUserQuestion that doesn't have a matching
      // tool_result yet. Without this, open questions from a task running
      // before the restart silently disappear from the inbox UI. The
      // reconstructed items won't be answerable until the task is
      // restarted (the Claude process is dead), but at least the user
      // sees them and understands what's pending.
      try {
        const chatHistoryDir = `${project.path}/.shipwright-webui/chat-history`;
        if (fs.existsSync(chatHistoryDir)) {
          const files = fs.readdirSync(chatHistoryDir).filter((f) => f.endsWith(".jsonl"));
          for (const file of files) {
            const taskId = file.replace(/\.jsonl$/, "");

            // Iterate 11 — skip replay for tasks that are terminal or
            // gone. No point surfacing inbox items the user can't
            // actually answer (process is dead). The route-level
            // filter hides them anyway but skipping here also keeps
            // the in-memory map clean.
            const task = taskManager.getTaskById(project.id, taskId);
            if (!task) continue;
            if (["done", "failed", "cancelled", "orphaned"].includes(task.status)) {
              continue;
            }

            const messages = await chatStore.load(project.path, taskId);
            const orphans = findOrphanAskUserQuestions(messages);
            for (const orphan of orphans) {
              // Skip if the inbox already knows this item (loadFromDisk
              // already picked it up from inbox.jsonl). Without this guard
              // persistItem would append a duplicate line for every restart.
              if (inboxManager.getById(orphan.toolUseId)) continue;
              await inboxManager.addQuestion(
                project.id,
                orphan.taskId,
                orphan.question,
                orphan.context,
                orphan.options,
                orphan.toolUseId,
                orphan.createdAt,
              );
            }
          }
        }
      } catch (err) {
        console.error(JSON.stringify({
          level: "warn",
          message: "Inbox chat-history replay failed",
          project: project.id,
          error: String(err),
        }));
      }


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


    // Cleanup orphans (governor-side: kill dead PIDs, clear pids.json).
    const orphanResult = await governor.cleanupOrphans();
    console.log("[boot] Orphan cleanup:", orphanResult);

    // Iterate 12.0b — construct the heartbeat NOW, with a reconciler
    // wired up to eventStore + projectManager + the event writer so
    // dead-PID detections persist as `task_orphaned` events. The
    // construction has to happen after projectManager is initialised
    // (the reconciler's resolveEventsPath closes over it). The early
    // `let` above makes the binding visible to the shutdown handler.
    heartbeat = new HeartbeatScheduler(
      governor,
      governorDeps,
      { schedule: cron.schedule },
      {
        onDeadProcess: (taskId, projectId) => {
          sseManager.broadcast({
            type: "task:updated",
            payload: { taskId, projectId },
            timestamp: new Date().toISOString(),
          });
        },
      },
      "*/30 * * * * *",
      {
        eventStore: {
          getTaskState: (taskId) => eventStore.getTaskState(taskId),
          addEvent: (projectId, event) => eventStore.addEvent(projectId, event),
        },
        resolveEventsPath: (projectId) => {
          const proj = projectManager.getAll().find((p) => p.id === projectId);
          return proj ? `${proj.path}/shipwright_events.jsonl` : undefined;
        },
        emitTaskOrphaned: (eventsPath, taskId, projectId, reason) =>
          emitTaskOrphanedEvent(eventsPath, taskId, projectId, reason, writerDeps),
      },
    );

    // Iterate 12.0b — startup reconciliation.
    // MUST run AFTER `governor.cleanupOrphans()` (otherwise we'd emit
    // false-positive orphan events for legitimately running tasks whose
    // PID file hadn't been cleaned yet) and BEFORE `heartbeat.start()`
    // (so the first tick sees the reconciled state). Walks every known
    // project's event-store tasks; any task still in `running` status
    // without a live process gets a `task_orphaned` event with reason
    // `stale_on_startup`. Errors are logged per-task and do not block
    // the rest of the boot sequence.
    for (const project of projectManager.getAll()) {
      const tasks = eventStore.getTasksForProject(project.id);
      const eventsPath = `${project.path}/shipwright_events.jsonl`;
      for (const task of tasks) {
        if (task.status !== "running") continue;
        const proc = governor.getProcess(task.id);
        if (proc && governorDeps.isProcessRunning(proc.pid)) continue;
        try {
          const event = await emitTaskOrphanedEvent(
            eventsPath,
            task.id,
            project.id,
            "stale_on_startup",
            writerDeps,
          );
          eventStore.addEvent(project.id, event);
        } catch (err) {
          console.error(JSON.stringify({
            level: "warn",
            message: "Startup orphan reconciliation failed",
            taskId: task.id,
            projectId: project.id,
            error: String(err),
          }));
        }
      }
    }

    heartbeat.start();

    // Settings deps
    const settingsDeps = {
      readFile: (p: string, e: string) => readFile(p, e as BufferEncoding),
      writeFile: (p: string, d: string) => writeFile(p, d),
      existsSync: (p: string) => fs.existsSync(p),
      mkdirSync: (p: string, o?: { recursive: boolean }) => fs.mkdirSync(p, o),
      lock: lockPath,
      ensureFile: ensureFileExists,
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
      chatStore,
      inboxManager,
      emitTaskCreatedEvent: (fp, tid, pid, desc, intent, priority, phase) =>
        emitTaskCreatedEvent(fp, tid, pid, desc, intent, priority, phase, writerDeps),
      emitPhaseStartedEvent: (fp, tid, pid, phase) =>
        emitPhaseStartedEvent(fp, tid, pid, phase, writerDeps),
      // Iterate 8 — persist task_cancelled / work_completed / task_updated to
      // shipwright_events.jsonl so deleted / closed / edited tasks survive a
      // server restart instead of being resurrected by the event replay.
      emitTaskCancelledEvent: (fp, tid, pid) =>
        emitTaskCancelledEvent(fp, tid, pid, writerDeps),
      emitWorkCompletedEvent: (fp, tid, pid) =>
        emitWorkCompletedEvent(fp, tid, pid, writerDeps),
      emitTaskUpdatedEvent: (fp, tid, pid, fields) =>
        emitTaskUpdatedEvent(fp, tid, pid, fields, writerDeps),
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
    // Iterate 11 — pass taskManager + projectManager so the inbox route
    // can filter out ghost items for terminal/nonexistent tasks.
    // Iterate 11.1 — also pass governor so zombie tasks (running in the
    // event store but no live process) get filtered too.
    app.route("/", createInboxRoutes(inboxManager, sseManager, taskManager, projectManager, governor));
    app.route("/", createChatRoutes(chatStore, governor, adapter, projectManager));
    app.route("/", createPipelineRoutes(eventStore, projectManager));
    app.route("/", createDocsRoutes(projectManager));
    app.route("/", createClassifyRoutes(projectManager));
    app.route("/", createSettingsRoutes(settingsPath, settingsDeps));
    app.route("/", createCapabilitiesRoutes());
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
