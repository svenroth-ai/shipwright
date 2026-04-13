import type { NdjsonMessage, ChatMessage } from "../../../client/src/types/chat.js";

export function parseNdjsonLine(line: string): NdjsonMessage | null {
  const trimmed = line.trim();
  if (!trimmed) return null;

  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed.type !== "string") return null;
    return parsed as NdjsonMessage;
  } catch {
    console.warn(JSON.stringify({ level: "warn", message: "Malformed NDJSON line skipped" }));
    return null;
  }
}

export function isAskUserQuestion(msg: NdjsonMessage): boolean {
  if (msg.type === "tool_use") {
    const toolName = msg.tool_name ?? (msg.message as { tool_name?: string } | undefined)?.tool_name;
    return toolName === "AskUserQuestion";
  }
  return false;
}

/**
 * Convert an NDJSON message into one or more ChatMessages.
 * Claude CLI emits various types: assistant (with content blocks), tool_use,
 * tool_result, result, system/init. An assistant message may contain mixed
 * content blocks (text, tool_use, thinking) — we split those into separate
 * ChatMessage entries so each renders independently.
 */
export function extractContentBlocks(
  taskId: string,
  msg: NdjsonMessage,
): ChatMessage[] {
  const now = new Date().toISOString();
  const makeId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // assistant messages — Claude CLI wraps content in { model, type, role, content: [...] }
  if (msg.type === "assistant") {
    const message = msg.message;

    // Simple string message
    if (typeof message === "string" && message.length > 0) {
      return [{
        id: makeId(), taskId, type: "assistant",
        content: message, timestamp: now,
      }];
    }

    // Object with content blocks (actual Claude CLI format):
    // { model: "...", type: "message", role: "assistant", content: [{type: "text", text: "..."}, ...] }
    if (message && typeof message === "object") {
      const msgObj = message as Record<string, unknown>;
      const model = msgObj.model as string | undefined;
      const content = msgObj.content;

      // content is an array of content blocks
      if (Array.isArray(content)) {
        return content.flatMap((block: Record<string, unknown>): ChatMessage[] => {
          if (block.type === "text" && typeof block.text === "string") {
            return [{
              id: makeId(), taskId, type: "assistant",
              content: block.text, model, timestamp: now,
            }];
          }
          if (block.type === "thinking" && typeof block.thinking === "string") {
            return [{
              id: makeId(), taskId, type: "thinking",
              content: block.thinking, model, timestamp: now,
            }];
          }
          if (block.type === "tool_use") {
            return [{
              id: makeId(), taskId, type: "tool_use",
              content: "",
              toolName: block.name as string,
              toolInput: block.input,
              toolUseId: typeof block.id === "string" ? block.id : undefined,
              model,
              timestamp: now,
            }];
          }
          return [];
        });
      }

      // content is a plain string
      if (typeof content === "string") {
        return [{
          id: makeId(), taskId, type: "assistant",
          content, model, timestamp: now,
        }];
      }
    }

    // Direct content block array (alternative format)
    if (Array.isArray(message)) {
      return message.flatMap((block: Record<string, unknown>): ChatMessage[] => {
        if (block.type === "text" && typeof block.text === "string") {
          return [{
            id: makeId(), taskId, type: "assistant",
            content: block.text, timestamp: now,
          }];
        }
        if (block.type === "thinking" && typeof block.thinking === "string") {
          return [{
            id: makeId(), taskId, type: "thinking",
            content: block.thinking, timestamp: now,
          }];
        }
        if (block.type === "tool_use") {
          return [{
            id: makeId(), taskId, type: "tool_use",
            content: "",
            toolName: block.name as string,
            toolInput: block.input,
            toolUseId: typeof block.id === "string" ? block.id : undefined,
            timestamp: now,
          }];
        }
        return [];
      });
    }

    return [];
  }

  // content_block events (streaming delta)
  if (msg.type === "content_block_start" || msg.type === "content_block_delta") {
    const block = msg.content_block;
    if (!block) return [];
    if (block.type === "thinking" && block.thinking) {
      return [{
        id: makeId(), taskId, type: "thinking",
        content: block.thinking, timestamp: now,
      }];
    }
    if (block.type === "text" && block.text) {
      return [{
        id: makeId(), taskId, type: "assistant",
        content: block.text, timestamp: now,
      }];
    }
    if (block.type === "tool_use") {
      return [{
        id: makeId(), taskId, type: "tool_use",
        content: "", toolName: block.name, toolInput: block.input,
        timestamp: now,
      }];
    }
    return [];
  }

  // tool_use — explicit tool invocation event
  if (msg.type === "tool_use") {
    const msgObj = msg.message as { tool_name?: string; tool_input?: unknown; id?: string } | undefined;
    const toolName = msg.tool_name ?? msgObj?.tool_name ?? "Tool";
    const toolInput = msg.tool_input ?? msgObj?.tool_input;
    const rawId = msg.id ?? msg.tool_use_id ?? msgObj?.id;
    return [{
      id: makeId(), taskId, type: "tool_use",
      content: "", toolName, toolInput,
      toolUseId: typeof rawId === "string" ? rawId : undefined,
      timestamp: now,
    }];
  }

  // tool_result — output from a tool
  if (msg.type === "tool_result") {
    const content = typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content ?? msg.message ?? "");
    const isError = msg.is_error === true || msg.subtype === "error";
    const rawRef = msg.tool_use_id;
    return [{
      id: makeId(), taskId, type: "tool_result",
      content, isError,
      toolUseId: typeof rawRef === "string" ? rawRef : undefined,
      timestamp: now,
    }];
  }

  // result — final summary message
  if (msg.type === "result") {
    const content = msg.result ?? (typeof msg.message === "string" ? msg.message : JSON.stringify(msg.message ?? ""));
    return [{
      id: makeId(), taskId, type: "result",
      content: typeof content === "string" ? content : JSON.stringify(content),
      timestamp: now,
    }];
  }

  // system / init — session metadata
  if (msg.type === "system" || msg.type === "init") {
    const content = typeof msg.message === "string" ? msg.message : JSON.stringify(msg.message ?? msg);
    const model = (msg as Record<string, unknown>).model as string | undefined;
    return [{
      id: makeId(), taskId, type: "system",
      content, model, timestamp: now,
    }];
  }

  return [];
}
