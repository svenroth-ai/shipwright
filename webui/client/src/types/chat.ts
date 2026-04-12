export type ChatMessageType = "assistant" | "tool_use" | "tool_result" | "result" | "user" | "system" | "thinking";

export interface ChatMessage {
  id: string;
  taskId: string;
  type: ChatMessageType;
  content: string;
  toolName?: string;
  toolInput?: unknown;
  toolOutput?: unknown;
  isError?: boolean;
  model?: string;
  timestamp: string;
}

export interface NdjsonMessage {
  type: string;
  message?: unknown;
  tool_name?: string;
  tool_input?: unknown;
  content?: string;
  content_block?: {
    type: string;
    text?: string;
    name?: string;
    input?: unknown;
    thinking?: string;
  };
  result?: string;
  session_id?: string;
  subtype?: string;
  is_error?: boolean;
  [key: string]: unknown;
}
