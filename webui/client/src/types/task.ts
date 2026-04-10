export type KanbanStatus = "backlog" | "in_progress" | "in_review" | "done" | "failed" | "cancelled";

export type TaskStatus = "pending" | "running" | "waiting" | "done" | "failed" | "orphaned" | "cancelled";

export type PhaseToStatusMapping = Record<string, KanbanStatus>;

export interface Task {
  id: string;
  projectId: string;
  description: string;
  intent?: string;
  priority?: string;
  complexity?: string;
  status: TaskStatus;
  kanbanStatus: KanbanStatus;
  currentPhase?: string;
  sessionId: string;
  pid?: number;
  exitCode?: number;
  createdAt: string;
  updatedAt: string;
}
