import type { ShipwrightEvent } from "../../../client/src/types/event.js";
import type { Task, TaskStatus } from "../../../client/src/types/task.js";
import type { PipelinePhase, PhaseStatus } from "../../../client/src/types/pipeline.js";

interface TaskStateEntry {
  id: string;
  projectId: string;
  title: string;
  description: string;
  status: TaskStatus;
  currentPhase?: string;
  requestedPhase?: string;
  intent?: string;
  priority?: string;
  sessionId: string;
  createdAt: string;
  updatedAt: string;
}

const PIPELINE_PHASES = ["project", "design", "plan", "build", "test", "changelog", "deploy"] as const;

export class EventStore {
  private events = new Map<string, ShipwrightEvent[]>();
  private taskStates = new Map<string, TaskStateEntry>();
  private phaseDedup = new Map<string, ShipwrightEvent>();
  private pipelinePhases = new Map<string, Map<string, { status: PhaseStatus; startedAt?: string; completedAt?: string; detail?: string }>>();

  replayProject(projectId: string, events: ShipwrightEvent[]): void {
    this.events.set(projectId, [...events]);
    for (const event of events) {
      this.processEvent(projectId, event);
    }
  }

  addEvent(projectId: string, event: ShipwrightEvent): void {
    const existing = this.events.get(projectId) ?? [];
    existing.push(event);
    this.events.set(projectId, existing);
    this.processEvent(projectId, event);
  }

  private processEvent(projectId: string, event: ShipwrightEvent): void {
    const taskId = event.task_id;

    switch (event.type) {
      case "task_created": {
        const rawDesc = (event.description as string) ?? "";
        const eventTitle = (event.title as string) ?? "";
        // Backward compat: if no title in event, extract from description (first line before \n\n)
        let title = eventTitle;
        let description = rawDesc;
        if (!title && rawDesc) {
          const splitIdx = rawDesc.indexOf("\n\n");
          if (splitIdx > 0) {
            title = rawDesc.slice(0, splitIdx);
            description = rawDesc.slice(splitIdx + 2);
          } else {
            title = rawDesc;
            description = "";
          }
        }
        this.taskStates.set(taskId, {
          id: taskId,
          projectId,
          title,
          description,
          status: "pending",
          intent: event.intent,
          priority: event.priority,
          requestedPhase: typeof event.phase === "string" ? event.phase : undefined,
          sessionId: (event.session_id as string) ?? taskId,
          createdAt: event.timestamp,
          updatedAt: event.timestamp,
        });
        break;
      }
      case "phase_started": {
        const task = this.taskStates.get(taskId);
        if (task) {
          task.status = "running";
          task.currentPhase = event.phase;
          task.updatedAt = event.timestamp;
        }
        if (event.phase) {
          this.updatePipelinePhase(projectId, event.phase, "running", event.timestamp);
        }
        break;
      }
      case "phase_completed": {
        if (event.phase) {
          const dedupKey = `${taskId}:${event.phase}`;
          const existing = this.phaseDedup.get(dedupKey);

          if (existing) {
            const timeDiff = Math.abs(
              new Date(event.timestamp).getTime() - new Date(existing.timestamp).getTime()
            );
            if (timeDiff <= 60_000) {
              // Within 60s: keep the one with detail
              if (event.detail && !existing.detail) {
                this.phaseDedup.set(dedupKey, event);
                this.updatePipelinePhase(projectId, event.phase, "completed", event.timestamp, event.detail as string | undefined);
              }
              // If existing has detail, keep it
              break;
            }
          }

          this.phaseDedup.set(dedupKey, event);
          this.updatePipelinePhase(projectId, event.phase, "completed", event.timestamp, event.detail as string | undefined);
        }
        break;
      }
      case "work_completed": {
        const task = this.taskStates.get(taskId);
        if (task) {
          task.status = "done";
          task.updatedAt = event.timestamp;
        }
        break;
      }
      case "work_failed": {
        const task = this.taskStates.get(taskId);
        if (task) {
          task.status = "failed";
          task.updatedAt = event.timestamp;
        }
        break;
      }
      case "task_updated": {
        const task = this.taskStates.get(taskId);
        if (task) {
          if (event.title) task.title = event.title as string;
          if (event.description !== undefined) task.description = event.description as string;
          task.updatedAt = event.timestamp;
        }
        break;
      }
      case "task_cancelled": {
        const task = this.taskStates.get(taskId);
        if (task) {
          task.status = "cancelled";
          task.updatedAt = event.timestamp;
        }
        break;
      }
      case "task_orphaned": {
        // Iterate 12.0b: applied when the heartbeat / startup
        // reconciliation detects a task whose Claude process is gone but
        // whose status is still "running" in the event store. Idempotency
        // rule (GPT review): only flip to orphaned if the task is still
        // running — prevents double-apply when startup reconciliation and
        // the first heartbeat tick both land before the next event flush,
        // and also prevents late-arriving orphan events from clobbering a
        // legitimate work_completed / work_failed that arrived first.
        const task = this.taskStates.get(taskId);
        if (!task) break;
        if (task.status !== "running") break;
        task.status = "orphaned";
        task.updatedAt = event.timestamp;
        break;
      }
    }
  }

  private updatePipelinePhase(
    projectId: string,
    phaseName: string,
    status: PhaseStatus,
    timestamp: string,
    detail?: string
  ): void {
    if (!this.pipelinePhases.has(projectId)) {
      this.pipelinePhases.set(projectId, new Map());
    }
    const phases = this.pipelinePhases.get(projectId)!;
    const existing = phases.get(phaseName) ?? { status: "pending" };

    if (status === "running") {
      existing.status = "running";
      existing.startedAt = timestamp;
    } else if (status === "completed") {
      existing.status = "completed";
      existing.completedAt = timestamp;
      if (detail) existing.detail = detail;
    }

    phases.set(phaseName, existing);
  }

  getTasksForProject(projectId: string): Task[] {
    return Array.from(this.taskStates.values())
      .filter((t) => t.projectId === projectId)
      .map((t) => ({
        ...t,
        kanbanStatus: "backlog" as const,
      }));
  }

  /**
   * Return the in-memory state entry for a task, or undefined.
   *
   * Added in iterate 12.0b so the heartbeat reconciler can check a task's
   * current status before emitting a `task_orphaned` event, without having
   * to reach into the private `taskStates` map directly. The heartbeat
   * uses this to avoid double-applying orphan events on tasks that have
   * already completed or been cancelled between ticks.
   */
  getTaskState(taskId: string): TaskStateEntry | undefined {
    return this.taskStates.get(taskId);
  }

  getPipelineState(projectId: string): PipelinePhase[] {
    const phases = this.pipelinePhases.get(projectId) ?? new Map();
    return PIPELINE_PHASES.map((name) => {
      const phase = phases.get(name);
      return {
        name,
        status: phase?.status ?? "pending",
        startedAt: phase?.startedAt,
        completedAt: phase?.completedAt,
        detail: phase?.detail,
      };
    });
  }
}
