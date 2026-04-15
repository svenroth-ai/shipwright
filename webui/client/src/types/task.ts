export type KanbanStatus =
  | "backlog"
  | "in_progress"
  | "in_review"
  | "done"
  | "failed"
  | "cancelled"
  | "interrupted";

export type TaskStatus =
  | "pending"
  | "running"
  | "waiting"
  | "done"
  | "failed"
  | "orphaned"
  | "interrupted"
  | "cancelled";

export type PhaseToStatusMapping = Record<string, KanbanStatus>;

export interface Task {
  id: string;
  projectId: string;
  title: string;
  description: string;
  intent?: string;
  priority?: string;
  complexity?: string;
  status: TaskStatus;
  kanbanStatus: KanbanStatus;
  currentPhase?: string;
  requestedPhase?: string;
  sessionId: string;
  /**
   * Real Claude Code CLI `session_id` captured from the `system/init`
   * NDJSON event on first spawn. Persisted via `session_captured` events
   * so that 14.7.0's "interrupted" path can `--resume <claudeSessionId>`
   * after a server restart. Undefined until Claude emits `system/init`.
   */
  claudeSessionId?: string;
  /**
   * Last `task_orphaned.detail` observed. `stale_on_startup` means the
   * server was restarted while the task was running (resumable if a
   * claudeSessionId is also present). `process_dead` means the CLI
   * exited abnormally mid-turn (not resumable).
   */
  orphanReason?: string;
  pid?: number;
  exitCode?: number;
  createdAt: string;
  updatedAt: string;
}
