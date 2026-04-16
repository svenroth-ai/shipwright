import type { Task, TaskStatus, KanbanStatus, PhaseToStatusMapping } from "../../../client/src/types/task.js";
import type { EventStore } from "./event-store.js";

/** Named constants for task_orphaned event detail values. Avoids string-literal
 *  typos across the codebase (heartbeat, startup reconciliation, interrupt). */
export const ORPHAN_REASONS = {
  STALE_ON_STARTUP: "stale_on_startup",
  PROCESS_DEAD: "process_dead",
  USER_INTERRUPTED: "user_interrupted",
} as const;

export const DEFAULT_PHASE_TO_STATUS_MAPPING: PhaseToStatusMapping = {
  project: "in_progress",
  design: "in_progress",
  plan: "in_progress",
  build: "in_progress",
  test: "in_review",
  security: "in_review",
  compliance: "in_review",
  changelog: "in_review",
  deploy: "in_review",
};

/**
 * Derive the kanban column for a task.
 *
 * Iterate 14.9 (Bug F1): resumable orphans (stale_on_startup +
 * user_interrupted with a captured claudeSessionId) now keep their
 * phase's natural column instead of being forced into a separate
 * "interrupted" bucket. TaskCard still renders the pause icon +
 * Resume/Cancel actions — it derives that flag from task.status +
 * task.orphanReason directly instead of reading kanbanStatus.
 *
 * Non-resumable orphans (process_dead, or missing claudeSessionId)
 * still collapse into "backlog" so they surface as something the user
 * can re-start explicitly.
 */
export function deriveKanbanStatus(
  task: {
    currentPhase?: string;
    status: TaskStatus;
    orphanReason?: string;
    claudeSessionId?: string;
  },
  mapping: PhaseToStatusMapping
): KanbanStatus {
  if (task.status === "done") return "done";
  if (task.status === "failed") return "failed";
  if (task.status === "cancelled") return "cancelled";

  if (task.status === "orphaned") {
    const isResumable =
      (task.orphanReason === ORPHAN_REASONS.STALE_ON_STARTUP ||
        task.orphanReason === ORPHAN_REASONS.USER_INTERRUPTED) &&
      !!task.claudeSessionId;

    if (isResumable) {
      // Stay in the phase's natural column (e.g. test → in_review) —
      // don't force "In Progress" just because the task is paused.
      if (task.currentPhase && mapping[task.currentPhase]) {
        return mapping[task.currentPhase];
      }
      return "in_progress";
    }

    return "backlog";
  }

  if (task.currentPhase && mapping[task.currentPhase]) {
    return mapping[task.currentPhase];
  }

  return "backlog";
}

export class TaskManager {
  constructor(private eventStore: EventStore) {}

  getTasksWithKanban(
    projectId: string,
    customMapping?: PhaseToStatusMapping
  ): Task[] {
    const mapping = this.resolveMapping(customMapping);
    return this.eventStore.getTasksForProject(projectId).map((task) => ({
      ...task,
      kanbanStatus: deriveKanbanStatus(task, mapping),
    }));
  }

  getTaskById(
    projectId: string,
    taskId: string,
    customMapping?: PhaseToStatusMapping
  ): Task | undefined {
    const mapping = this.resolveMapping(customMapping);
    const task = this.eventStore
      .getTasksForProject(projectId)
      .find((t) => t.id === taskId);
    if (!task) return undefined;
    return { ...task, kanbanStatus: deriveKanbanStatus(task, mapping) };
  }

  getTasksByStatus(
    projectId: string,
    kanbanStatus: KanbanStatus,
    customMapping?: PhaseToStatusMapping
  ): Task[] {
    return this.getTasksWithKanban(projectId, customMapping).filter(
      (t) => t.kanbanStatus === kanbanStatus
    );
  }

  resolveMapping(projectMapping?: PhaseToStatusMapping): PhaseToStatusMapping {
    return { ...DEFAULT_PHASE_TO_STATUS_MAPPING, ...projectMapping };
  }
}
