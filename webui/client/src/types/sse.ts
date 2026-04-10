export type SSEEventType =
  | "project:updated"
  | "task:created"
  | "task:updated"
  | "inbox:new"
  | "inbox:answered"
  | "chat:message"
  | "pipeline:updated";

export interface SSEEvent<T = unknown> {
  type: SSEEventType;
  payload: T;
  timestamp: string;
}
