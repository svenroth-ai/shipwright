import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { TaskManager } from "../core/task-manager.js";
import type { EventStore } from "../core/event-store.js";
import type { ProcessGovernor } from "../core/process-governor.js";
import type { ClaudeAdapter, PermissionMode, ModelAlias } from "../core/claude-adapter.js";
import { wrapWithEffort, coerceEffort } from "../core/effort-prompt.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { ProjectManager } from "../core/project-manager.js";
import type { ChatStore } from "../core/chat-store.js";
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

    const permissionMode = coercePermissionMode(body.mode);
    const model = coerceModel(body.model);
    const effort = coerceEffort(body.effort);
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
          prompt: wrapWithEffort(buildPrompt(title, description), effort),
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
    const effort = coerceEffort(body.effort);
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
        prompt: wrapWithEffort(buildPrompt(task.title, task.description), effort),
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

  return app;
}
