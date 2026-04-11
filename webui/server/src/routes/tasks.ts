import { Hono } from "hono";
import { randomUUID } from "crypto";
import type { TaskManager } from "../core/task-manager.js";
import type { EventStore } from "../core/event-store.js";
import type { ProcessGovernor } from "../core/process-governor.js";
import type { ClaudeAdapter } from "../core/claude-adapter.js";
import type { SSEManager } from "../core/sse-manager.js";
import type { ProjectManager } from "../core/project-manager.js";
import { AppError } from "../middleware/error-handler.js";

export interface TaskRouteDeps {
  taskManager: TaskManager;
  eventStore: EventStore;
  governor: ProcessGovernor;
  adapter: ClaudeAdapter;
  sseManager: SSEManager;
  projectManager: ProjectManager;
  emitTaskCreatedEvent: (
    filePath: string,
    taskId: string,
    projectId: string,
    description: string,
    intent?: string,
    priority?: string
  ) => Promise<unknown>;
  readGlobalSettings?: () => Promise<Record<string, unknown>>;
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
    if (!body.description) throw new AppError("description is required", 400);

    const startImmediately = body.startImmediately !== false; // default true
    const taskId = randomUUID();
    const sessionId = randomUUID();
    const eventsPath = `${project.path}/shipwright_events.jsonl`;

    await deps.emitTaskCreatedEvent(eventsPath, taskId, project.id, body.description, body.intent, body.priority);
    deps.eventStore.addEvent(project.id, {
      type: "task_created",
      timestamp: new Date().toISOString(),
      task_id: taskId,
      project_id: project.id,
      description: body.description,
    });

    if (startImmediately) {
      const result = await deps.governor.acquire({
        projectDir: project.path,
        projectId: project.id,
        taskId,
        sessionId,
        resume: false,
        pluginDirs: project.settings?.claudePluginDirs ?? [],
        prompt: body.description,
      });

      if (result === "queued") {
        return c.json({ data: { taskId, status: "queued" } }, 202);
      }
    }

    const mapping = await getPhaseMapping(project.settings);
    const task = deps.taskManager.getTasksWithKanban(project.id, mapping).find((t) => t.id === taskId);
    return c.json({ data: task ?? { id: taskId, status: "pending" } }, 201);
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
    const result = await deps.governor.acquire({
      projectDir: project.path,
      projectId: project.id,
      taskId,
      sessionId,
      resume: true,
      pluginDirs: project.settings?.claudePluginDirs ?? [],
      prompt: task.description,
    });

    if (result === "queued") {
      return c.json({ data: { taskId, status: "queued" } }, 202);
    }

    return c.json({ data: { taskId, status: "running" } });
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
