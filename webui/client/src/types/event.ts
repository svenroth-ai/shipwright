export type EventType =
  | "task_created"
  | "phase_started"
  | "phase_completed"
  | "work_completed"
  | "work_failed"
  | "task_cancelled";

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
