export type EventType =
  | "task_created"
  | "task_updated"
  | "phase_started"
  | "phase_completed"
  | "work_completed"
  | "work_failed"
  | "task_cancelled"
  | "task_orphaned"
  | "session_captured"
  | "task_resumed";

export interface ShipwrightEvent {
  type: EventType;
  timestamp: string;
  task_id: string;
  project_id?: string;
  phase?: string;
  detail?: string;
  source?: string;
  description?: string;
  intent?: string;
  priority?: string;
  [key: string]: unknown;
}
