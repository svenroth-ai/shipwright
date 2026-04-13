export type ChatMessageType = "assistant" | "tool_use" | "tool_result" | "result" | "user" | "system" | "thinking";

export interface ChatImage {
  media_type: string;
  data: string; // base64 (no data: prefix)
}

export interface ChatMessage {
  id: string;
  taskId: string;
  type: ChatMessageType;
  content: string;
  toolName?: string;
  toolInput?: unknown;
  toolOutput?: unknown;
  /** Anthropic API tool_use_id — used to fold tool_result into its matching tool_use card */
  toolUseId?: string;
  isError?: boolean;
  model?: string;
  images?: ChatImage[];
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
