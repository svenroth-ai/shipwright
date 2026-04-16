import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { TaskManager } from "../core/task-manager.js";
import type { EventStore } from "../core/event-store.js";
import type { ProcessGovernor } from "../core/process-governor.js";
import type { ClaudeAdapter, PermissionMode, ModelAlias } from "../core/claude-adapter.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { ProjectManager } from "../core/project-manager.js";
import type { ChatStore } from "../core/chat-store.js";
import type { InboxManager } from "../core/inbox-manager.js";
import { AppError } from "../middleware/error-handler.js";
import { classifyPhase, VALID_PHASES, type Phase } from "../bridge/intent-classifier.js";

export interface TaskRouteDeps {
  taskManager: TaskManager;
  eventStore: EventStore;
  governor: ProcessGovernor;
  adapter: ClaudeAdapter;
  sseManager: SSEManager;
  projectManager: ProjectManager;
  chatStore?: ChatStore;
  /** Iterate 10 — the mode-switch endpoint needs to check for pending
   *  AskUserQuestion items before it's safe to respawn the process. */
  inboxManager?: InboxManager;
  emitTaskCreatedEvent: (
    filePath: string,
    taskId: string,
    projectId: string,
    description: string,
    intent?: string,
    priority?: string,
    phase?: string
  ) => Promise<unknown>;
  emitPhaseStartedEvent?: (
    filePath: string,
    taskId: string,
    projectId: string,
    phase: string
  ) => Promise<unknown>;
  /** Iterate 8 — persist task_cancelled to shipwright_events.jsonl so
   *  deleted tasks don't reappear after a server restart. */
  emitTaskCancelledEvent?: (
    filePath: string,
    taskId: string,
    projectId: string,
  ) => Promise<unknown>;
  /** Iterate 8 — persist work_completed for manual "Close" action
   *  so closed tasks stay closed across restarts. */
  emitWorkCompletedEvent?: (
    filePath: string,
    taskId: string,
    projectId: string,
  ) => Promise<unknown>;
  /** Iterate 8 — persist task_updated so description / title edits
   *  survive restarts (without this the edit is memory-only). */
  emitTaskUpdatedEvent?: (
    filePath: string,
    taskId: string,
    projectId: string,
    fields: { title?: string; description?: string },
  ) => Promise<unknown>;
  /** Iterate 14.7.0 — persist task_resumed so the resume endpoint's
   *  status transition (interrupted → running) survives restarts. */
  emitTaskResumedEvent?: (
    filePath: string,
    taskId: string,
    projectId: string,
    sessionId: string,
  ) => Promise<unknown>;
  readGlobalSettings?: () => Promise<Record<string, unknown>>;
}

function buildPrompt(title: string, description?: string): string {
  if (description) return `${title} — ${description}`;
  return title;
}

const VALID_PERMISSION_MODES: PermissionMode[] = ["default", "acceptEdits", "plan", "bypassPermissions"];
function coercePermissionMode(raw: unknown): PermissionMode {
  if (typeof raw === "string" && (VALID_PERMISSION_MODES as string[]).includes(raw)) {
    return raw as PermissionMode;
  }
  return "bypassPermissions";
}

const VALID_MODELS: ModelAlias[] = ["opus", "sonnet", "haiku"];
function coerceModel(raw: unknown): ModelAlias | undefined {
  if (typeof raw === "string" && (VALID_MODELS as string[]).includes(raw)) {
    return raw as ModelAlias;
  }
  return undefined;
}

// Iterate 14.8.2 — map concrete model id (stored in settings) to the
// coarse CLI alias accepted by `claude --model <alias>`.
const CONCRETE_TO_ALIAS: Record<string, ModelAlias> = {
  "claude-opus-4-6": "opus",
  "claude-opus-4-5": "opus",
  "claude-sonnet-4-6": "sonnet",
  "claude-sonnet-4-5": "sonnet",
  "claude-haiku-4-5": "haiku",
};
function aliasFromConcrete(concreteId: string): ModelAlias | undefined {
  return CONCRETE_TO_ALIAS[concreteId];
}

function coercePhase(raw: unknown): Phase | undefined {
  if (typeof raw === "string" && (VALID_PHASES as readonly string[]).includes(raw)) {
    return raw as Phase;
  }
  return undefined;
}

async function resolvePhase(
  raw: unknown,
  title: string,
  description: string,
  projectPath: string
): Promise<Phase> {
  const explicit = coercePhase(raw);
  if (explicit) return explicit;
  try {
    const result = await classifyPhase(`${title} ${description}`.trim(), projectPath);
    return (coercePhase(result.phase) ?? "project") as Phase;
  } catch {
    return "project";
  }
}

export function createTaskRoutes(deps: TaskRouteDeps): Hono {
  const app = new Hono();

  // Helper: get phase mapping from global settings or project override
  async function getPhaseMapping(projectSettings?: { phaseToStatusMapping?: Record<string, string> }) {
    // Per-project override takes precedence
    if (projectSettings?.phaseToStatusMapping) {
      return projectSettings.phaseToStatusMapping as Record<string, "backlog" | "in_progress" | "in_review" | "done" | "failed" | "cancelled">;
    }
    // Then try global settings
    if (deps.readGlobalSettings) {
      try {
        const settings = await deps.readGlobalSettings();
        if (settings.phaseToStatusMapping) {
          return settings.phaseToStatusMapping as Record<string, "backlog" | "in_progress" | "in_review" | "done" | "failed" | "cancelled">;
        }
      } catch {
        // Fall through to default
      }
    }
    return undefined;
  }

  app.get("/api/tasks", async (c) => {
    const allProjects = deps.projectManager.getAll();
    const globalMapping = await getPhaseMapping();
    const allTasks = allProjects.flatMap((project) =>
      deps.taskManager.getTasksWithKanban(
        project.id,
        project.settings?.phaseToStatusMapping ?? globalMapping
      )
    );
    return c.json({ data: allTasks });
  });

  app.get("/api/projects/:id/tasks", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const mapping = await getPhaseMapping(project.settings);
    const tasks = deps.taskManager.getTasksWithKanban(project.id, mapping);
    return c.json({ data: tasks });
  });

  app.post("/api/projects/:id/tasks", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const body = await c.req.json();
    const title = body.title || body.description;
    if (!title) throw new AppError("title or description is required", 400);
    const description = body.description ?? "";

    const startImmediately = body.startImmediately !== false; // default true
    const taskId = randomUUID();
    const sessionId = randomUUID();
    const eventsPath = `${project.path}/shipwright_events.jsonl`;

    // Iterate 14.8.2 — apply global defaults from settings when body
    // doesn't specify model or mode explicitly.
    let resolvedMode = body.mode;
    let resolvedModel = body.model;
    if ((!resolvedMode || !resolvedModel) && deps.readGlobalSettings) {
      try {
        const globalSettings = await deps.readGlobalSettings();
        if (!resolvedMode && globalSettings.defaultMode) {
          resolvedMode = globalSettings.defaultMode;
        }
        if (!resolvedModel && globalSettings.defaultModel) {
          resolvedModel = aliasFromConcrete(globalSettings.defaultModel as string);
        }
      } catch {
        // Fall through to hardcoded defaults
      }
    }
    const permissionMode = coercePermissionMode(resolvedMode);
    const model = coerceModel(resolvedModel);
    const phase = await resolvePhase(body.phase, title, description, project.path);

    await deps.emitTaskCreatedEvent(eventsPath, taskId, project.id, description, body.intent, body.priority, phase);
    deps.eventStore.addEvent(project.id, {
      type: "task_created",
      timestamp: new Date().toISOString(),
      task_id: taskId,
      project_id: project.id,
      title,
      description,
      phase,
    });

    let startStatus: "started" | "queued" | "failed" = "started";
    if (startImmediately) {
      try {
        const result = await deps.governor.acquire({
          projectDir: project.path,
          projectId: project.id,
          taskId,
          sessionId,
          pluginDirs: project.settings?.claudePluginDirs ?? [],
          prompt: buildPrompt(title, description),
          permissionMode,
          ...(model && { model }),
        });
        if (result === "queued") {
          startStatus = "queued";
        } else {
          // Emit phase_started so kanban updates to "in_progress"
          deps.eventStore.addEvent(project.id, {
            type: "phase_started",
            timestamp: new Date().toISOString(),
            task_id: taskId,
            project_id: project.id,
            phase,
          });
          if (deps.emitPhaseStartedEvent) {
            await deps.emitPhaseStartedEvent(eventsPath, taskId, project.id, phase);
          }
          deps.sseManager.broadcast({
            type: "task:updated",
            payload: { taskId, projectId: project.id },
            timestamp: new Date().toISOString(),
          });
        }
      } catch (err) {
        // Task is created even if Claude CLI spawn fails
        console.error(JSON.stringify({ level: "warn", message: "Task created but process spawn failed", taskId, error: String(err) }));
        startStatus = "failed";
      }
    }

    const mapping = await getPhaseMapping(project.settings);
    const task = deps.taskManager.getTasksWithKanban(project.id, mapping).find((t) => t.id === taskId);
    const status = startStatus === "queued" ? 202 : 201;
    return c.json({ data: task ?? { id: taskId, projectId: project.id, title, description, status: "pending", kanbanStatus: "backlog", createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), sessionId }, startStatus }, status);
  });

  // Fix 4: Start a pending task
  app.post("/api/projects/:id/tasks/:taskId/start", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);

    const taskId = c.req.param("taskId");
    const task = deps.taskManager.getTaskById(project.id, taskId);
    if (!task) throw new AppError("Task not found", 404);

    // Check if already running
    const proc = deps.governor.getProcess(taskId);
    if (proc && proc.state !== "exited") {
      throw new AppError("Task is already running", 409);
    }

    const sessionId = randomUUID();
    const eventsPath = `${project.path}/shipwright_events.jsonl`;
    const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
    const permissionMode = coercePermissionMode(body.mode);
    const model = coerceModel(body.model);
    // Resolve phase: explicit body.phase > task.requestedPhase > classify fallback > "project"
    const startPhase = await resolvePhase(
      body.phase ?? task.requestedPhase,
      task.title,
      task.description ?? "",
      project.path
    );
    try {
      const result = await deps.governor.acquire({
        projectDir: project.path,
        projectId: project.id,
        taskId,
        sessionId,
        pluginDirs: project.settings?.claudePluginDirs ?? [],
        prompt: buildPrompt(task.title, task.description),
        permissionMode,
        ...(model && { model }),
      });

      if (result === "queued") {
        return c.json({ data: { taskId, status: "queued" } }, 202);
      }

      // Emit phase_started so kanban updates using the resolved phase
      deps.eventStore.addEvent(project.id, {
        type: "phase_started",
        timestamp: new Date().toISOString(),
        task_id: taskId,
        project_id: project.id,
        phase: startPhase,
      });
      if (deps.emitPhaseStartedEvent) {
        await deps.emitPhaseStartedEvent(eventsPath, taskId, project.id, startPhase);
      }
      deps.sseManager.broadcast({
        type: "task:updated",
        payload: { taskId, projectId: project.id },
        timestamp: new Date().toISOString(),
      });

      return c.json({ data: { taskId, status: "running" } });
    } catch (err) {
      console.error(JSON.stringify({ level: "warn", message: "Task start failed", taskId, error: String(err) }));
      return c.json({ data: { taskId, status: "start_failed", error: String(err) } }, 500);
    }
  });

  app.patch("/api/projects/:id/tasks/:taskId/description", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const body = await c.req.json();
    if (!body.title && !body.description) {
      throw new AppError("title or description is required", 400);
    }

    const taskId = c.req.param("taskId");
    const task = deps.taskManager.getTaskById(project.id, taskId);
    if (!task) throw new AppError("Task not found", 404);
    if (task.status !== "pending") {
      throw new AppError("Can only edit description of pending tasks", 409);
    }

    // Persist the task_updated event to disk FIRST so description/title
    // edits survive a server restart. Without this the edit is memory-only
    // and the next replay reconstructs the task from the original event.
    const eventsPath = `${project.path}/shipwright_events.jsonl`;
    const fields: { title?: string; description?: string } = {
      ...(body.title && { title: body.title }),
      ...(body.description !== undefined && { description: body.description }),
    };
    if (deps.emitTaskUpdatedEvent) {
      await deps.emitTaskUpdatedEvent(eventsPath, taskId, project.id, fields);
    }
    deps.eventStore.addEvent(project.id, {
      type: "task_updated",
      timestamp: new Date().toISOString(),
      task_id: taskId,
      ...fields,
    });

    deps.sseManager.broadcast({
      type: "task:updated",
      payload: { taskId, projectId: project.id },
      timestamp: new Date().toISOString(),
    });

    const updated = deps.taskManager.getTaskById(project.id, taskId);
    return c.json({ data: updated });
  });

  app.patch("/api/projects/:id/tasks/:taskId/status", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);
    const body = await c.req.json();
    if (!body.status || !["closed", "cancelled"].includes(body.status)) {
      throw new AppError("status must be 'closed' or 'cancelled'", 400);
    }

    const taskId = c.req.param("taskId");
    const task = deps.taskManager.getTaskById(project.id, taskId);
    if (!task) throw new AppError("Task not found", 404);

    const eventType = body.status === "cancelled" ? "task_cancelled" : "work_completed";

    // Persist to disk FIRST so deleted/closed tasks don't reappear on restart.
    // In-memory EventStore update follows so the SSE broadcast reflects the
    // authoritative state.
    const eventsPath = `${project.path}/shipwright_events.jsonl`;
    if (eventType === "task_cancelled" && deps.emitTaskCancelledEvent) {
      await deps.emitTaskCancelledEvent(eventsPath, taskId, project.id);
    } else if (eventType === "work_completed" && deps.emitWorkCompletedEvent) {
      await deps.emitWorkCompletedEvent(eventsPath, taskId, project.id);
    }

    deps.eventStore.addEvent(project.id, {
      type: eventType,
      timestamp: new Date().toISOString(),
      task_id: taskId,
      source: "manual",
    });

    deps.sseManager.broadcast({
      type: "task:updated",
      payload: { taskId, projectId: project.id },
      timestamp: new Date().toISOString(),
    });

    const updated = deps.taskManager.getTaskById(project.id, taskId);
    return c.json({ data: updated });
  });

  // Iterate 14.1 — start /shipwright-preview as a background task.
  //
  // Reuses the same task-create + governor.acquire pattern as the normal
  // "Start immediately" POST /api/projects/:id/tasks flow. The prompt is
  // the literal slash command "/shipwright-preview"; Claude CLI resolves
  // that to the installed shipwright-preview plugin. Requires hasPreview
  // on the project (profile declares a dev_server.command) otherwise 403.
  //
  // Route lives in tasks.ts (not projects.ts) because the spawn path needs
  // governor/adapter/eventStore/etc. which are already wired here. Path
  // still reads /api/projects/:id/preview for the client.
  app.post("/api/projects/:id/preview", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);

    if (project.hasPreview !== true) {
      throw new AppError(
        "Project has no preview capability — profile lacks dev_server.command",
        403,
      );
    }

    const taskId = randomUUID();
    const sessionId = randomUUID();
    const eventsPath = `${project.path}/shipwright_events.jsonl`;
    const title = "Preview — start dev server";
    const description = "Start the local dev server and show the browser preview URL.";
    const phase: Phase = "preview" as Phase;
    const permissionMode: PermissionMode = "bypassPermissions";

    await deps.emitTaskCreatedEvent(
      eventsPath,
      taskId,
      project.id,
      description,
      "preview",
      undefined,
      phase,
    );
    deps.eventStore.addEvent(project.id, {
      type: "task_created",
      timestamp: new Date().toISOString(),
      task_id: taskId,
      project_id: project.id,
      title,
      description,
      phase,
    });

    let startStatus: "started" | "queued" | "failed" = "started";
    try {
      const result = await deps.governor.acquire({
        projectDir: project.path,
        projectId: project.id,
        taskId,
        sessionId,
        pluginDirs: project.settings?.claudePluginDirs ?? [],
        prompt: "/shipwright-preview",
        permissionMode,
      });
      if (result === "queued") {
        startStatus = "queued";
      } else {
        deps.eventStore.addEvent(project.id, {
          type: "phase_started",
          timestamp: new Date().toISOString(),
          task_id: taskId,
          project_id: project.id,
          phase,
        });
        if (deps.emitPhaseStartedEvent) {
          await deps.emitPhaseStartedEvent(eventsPath, taskId, project.id, phase);
        }
        deps.sseManager.broadcast({
          type: "task:updated",
          payload: { taskId, projectId: project.id },
          timestamp: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error(JSON.stringify({
        level: "warn",
        message: "Preview task created but process spawn failed",
        taskId,
        error: String(err),
      }));
      startStatus = "failed";
    }

    return c.json({ data: { taskId, startStatus } }, 202);
  });

  // Iterate 14.7.0 — resume a task that was interrupted by a server
  // restart. Distinct from the `/mode` endpoint: that one respawns a
  // still-running process to change permission mode, this one brings
  // a dead process back to life using the persisted claudeSessionId.
  //
  // Preconditions:
  //   - task exists for this project
  //   - task's derived kanbanStatus === "interrupted" (so we know the
  //     reconciliation loop tagged it as resumable, and the captured
  //     claudeSessionId is present on task state)
  //
  // On success: emits `task_resumed` event, spawns Claude with
  // `--resume <claudeSessionId>`, returns 202 with `running`.
  app.post("/api/projects/:id/tasks/:taskId/resume", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);

    const taskId = c.req.param("taskId");
    const mapping = await getPhaseMapping(project.settings);
    const task = deps.taskManager.getTaskById(project.id, taskId, mapping);
    if (!task) throw new AppError("Task not found", 404);

    if (task.kanbanStatus !== "interrupted") {
      throw new AppError("task not interrupted", 404);
    }

    const claudeSessionId = task.claudeSessionId;
    if (!claudeSessionId) {
      // Defence-in-depth: deriveKanbanStatus only returns "interrupted"
      // when claudeSessionId is present, but guard anyway so a stale
      // client-side payload can't crash the spawn path.
      throw new AppError("task has no captured Claude session", 409);
    }

    const eventsPath = `${project.path}/shipwright_events.jsonl`;

    try {
      const result = await deps.governor.acquire({
        projectDir: project.path,
        projectId: project.id,
        taskId,
        sessionId: claudeSessionId,
        resumeSession: true,
        pluginDirs: project.settings?.claudePluginDirs ?? [],
        prompt: "", // Claude has the full history from --resume
        permissionMode: "bypassPermissions",
      });

      // Emit task_resumed to persist the transition. Do this AFTER a
      // successful spawn so a failed governor.acquire doesn't leave a
      // misleading "running" entry in the event log.
      if (deps.emitTaskResumedEvent) {
        await deps.emitTaskResumedEvent(eventsPath, taskId, project.id, claudeSessionId);
      }
      deps.eventStore.addEvent(project.id, {
        type: "task_resumed",
        timestamp: new Date().toISOString(),
        task_id: taskId,
        project_id: project.id,
        session_id: claudeSessionId,
      });

      deps.sseManager.broadcast({
        type: "task:updated",
        payload: { taskId, projectId: project.id },
        timestamp: new Date().toISOString(),
      });

      return c.json(
        {
          data: {
            taskId,
            status: result === "queued" ? "queued" : "running",
          },
        },
        202,
      );
    } catch (err) {
      console.error(JSON.stringify({
        level: "warn",
        message: "Task resume spawn failed",
        taskId,
        error: String(err),
      }));
      throw new AppError(`Resume failed: ${String(err)}`, 500);
    }
  });

  // Iterate 10 — mid-task permission mode switching via --resume respawn.
  // Supersedes ADR-011's "v0.1 not supported" stance: a single cold-start
  // respawn is fine for an explicit user action (unlike per-message respawn
  // which was the reason ADR-009 rejected the --resume approach).
  app.post("/api/projects/:id/tasks/:taskId/mode", async (c) => {
    const project = deps.projectManager.getById(c.req.param("id"));
    if (!project) throw new AppError("Project not found", 404);

    const body = await c.req.json().catch(() => ({} as Record<string, unknown>));
    const rawMode = body.mode;
    if (!rawMode || typeof rawMode !== "string" || !(VALID_PERMISSION_MODES as string[]).includes(rawMode)) {
      throw new AppError(
        `mode must be one of ${VALID_PERMISSION_MODES.join(", ")}`,
        400,
      );
    }
    const newMode = rawMode as PermissionMode;

    const taskId = c.req.param("taskId");
    const task = deps.taskManager.getTaskById(project.id, taskId);
    if (!task) throw new AppError("Task not found", 404);

    const proc = deps.governor.getProcess(taskId);
    if (!proc || proc.state === "exited") {
      throw new AppError("Task is not running — cannot switch mode", 400);
    }

    // Guard 1: the captured real Claude session_id must be available.
    // If not yet captured (process still in first few hundred ms) we can't
    // resume — tell the client to try again in a second.
    if (!proc.claudeSessionId) {
      throw new AppError(
        "Session not yet established — try again in a second",
        409,
      );
    }

    // Guard 2: don't respawn while a pending AskUserQuestion is waiting.
    // The respawned process would lose the tool_use correlation and the
    // question would be orphaned. The mode switch only applies cleanly
    // to the next decision point.
    if (deps.inboxManager) {
      const projectInbox = deps.inboxManager.getByProject(project.id);
      const pendingForTask = projectInbox.some(
        (item) => item.taskId === taskId && item.status === "pending",
      );
      if (pendingForTask) {
        throw new AppError(
          "Answer the pending question before switching mode",
          409,
        );
      }
    }

    // All clear — terminate current process and respawn with --resume.
    const claudeSessionId = proc.claudeSessionId;
    deps.adapter.terminate(proc);
    await deps.governor.release(taskId);

    const result = await deps.governor.acquire({
      projectDir: project.path,
      projectId: project.id,
      taskId,
      sessionId: claudeSessionId,
      resumeSession: true,
      pluginDirs: project.settings?.claudePluginDirs ?? [],
      prompt: "", // empty placeholder; Claude already has the full history
      permissionMode: newMode,
    });

    deps.sseManager.broadcast({
      type: "task:updated",
      payload: { taskId, projectId: project.id, modeChanged: newMode },
      timestamp: new Date().toISOString(),
    });

    return c.json({
      data: {
        taskId,
        permissionMode: newMode,
        status: result === "queued" ? "queued" : "running",
      },
    });
  });

  return app;
}
