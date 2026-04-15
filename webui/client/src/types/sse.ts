import type { ChatMessage } from "./chat";

export type SSEEventType =
  | "project:updated"
  | "task:created"
  | "task:updated"
  | "inbox:new"
  | "inbox:answered"
  | "inbox:flag_not_blocked"
  | "chat:message"
  | "pipeline:updated";

/** Iterate 14.5 — payload for `inbox:flag_not_blocked` SSE broadcasts. */
export interface InboxFlagNotBlockedPayload {
  inboxItemId: string;
  toolUseId: string;
  reason: "continued" | "turn_ended";
}

export interface SSEEvent<T = unknown> {
  type: SSEEventType;
  payload: T;
  timestamp: string;
}

/**
 * Iterate 13 / Phase 0: when SHIPWRIGHT_NEW_CHAT_PROTOCOL=1, the server emits
 * extracted ChatMessage objects over the chat:message SSE event (instead of
 * raw NdjsonMessage). Same stable id space as REST GET /chat so mergeCommitted
 * can dedupe by id without synthetic-id reconciliation. See plan
 * vast-mapping-petal.md.
 */
export interface ChatMessageSSEPayload {
  taskId: string;
  projectId: string;
  message: ChatMessage;
}
