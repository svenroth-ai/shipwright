import type { Task, TaskStatus, KanbanStatus, PhaseToStatusMapping } from "../../../client/src/types/task.js";
import type { EventStore } from "./event-store.js";

export const DEFAULT_PHASE_TO_STATUS_MAPPING: PhaseToStatusMapping = {
  project: "backlog",
  design: "backlog",
  plan: "backlog",
  build: "in_progress",
  test: "in_review",
  deploy: "done",
  changelog: "done",
  done: "done",
};

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

  // Iterate 14.7.0 — split orphan into `interrupted` (resumable, server
  // restart killed the process) vs `backlog` (not resumable: process
  // crashed mid-turn, or we never captured a real claudeSessionId so
  // --resume would fail).
  if (task.status === "orphaned") {
    if (task.orphanReason === "stale_on_startup" && task.claudeSessionId) {
      return "interrupted";
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
