export type ChatMessageType = "assistant" | "tool_use" | "tool_result" | "result" | "user" | "system";

export interface ChatMessage {
  id: string;
  taskId: string;
  type: ChatMessageType;
  content: string;
  toolName?: string;
  toolInput?: unknown;
  toolOutput?: unknown;
  timestamp: string;
}

export interface NdjsonMessage {
  type: string;
  message?: unknown;
  tool_name?: string;
  tool_input?: unknown;
  content?: string;
  result?: string;
  session_id?: string;
  [key: string]: unknown;
}
