/*
 * Server-side session JSONL parser.
 *
 * Used by inbox-derive (server-side) to inspect tool_use / tool_result
 * correlation across an entire JSONL. Client has its own renderer-oriented
 * parser at webui/client/src/poc-external/session-parser.ts (promoted to
 * the final shape in Sub-iterate 2). The two parsers intentionally share
 * no code because the workspaces don't share a tsconfig rootDir; the
 * schemas are small and the drift risk is low.
 *
 * Unknown top-level types pass through as `{ kind: "unknown", raw }` so
 * future CLI additions (slash events, plan events, custom plugin hooks)
 * are never silently dropped.
 */

export type ParsedSessionEvent =
  | UserEvent
  | AssistantEvent
  | AttachmentEvent
  | QueueOpEvent
  | FileSnapshotEvent
  | AiTitleEvent
  | LastPromptEvent
  | SystemEvent
  | CustomTitleEvent
  | AgentNameEvent
  | PermissionModeEvent
  | UnknownEvent;

export interface BaseSessionEvent {
  sessionId?: string;
  timestamp?: string;
  uuid?: string;
  parentUuid?: string | null;
}

export interface UserEvent extends BaseSessionEvent {
  kind: "user";
  content: unknown;
}

export interface AssistantEvent extends BaseSessionEvent {
  kind: "assistant";
  content: unknown;
  model?: string;
}

export interface AttachmentEvent extends BaseSessionEvent {
  kind: "attachment";
  attachment: unknown;
}

export interface QueueOpEvent extends BaseSessionEvent {
  kind: "queue-operation";
  operation: string;
  detail?: unknown;
}

export interface FileSnapshotEvent extends BaseSessionEvent {
  kind: "file-history-snapshot";
  snapshot: unknown;
  isSnapshotUpdate?: boolean;
}

export interface AiTitleEvent extends BaseSessionEvent {
  kind: "ai-title";
  title: string;
}

export interface LastPromptEvent extends BaseSessionEvent {
  kind: "last-prompt";
  prompt: unknown;
}

export interface SystemEvent extends BaseSessionEvent {
  kind: "system";
  text: string;
  subtype?: string;
}

export interface CustomTitleEvent extends BaseSessionEvent {
  kind: "custom-title";
  title: string;
}

export interface AgentNameEvent extends BaseSessionEvent {
  kind: "agent-name";
  name: string;
}

export interface PermissionModeEvent extends BaseSessionEvent {
  kind: "permission-mode";
  mode: string;
}

export interface UnknownEvent extends BaseSessionEvent {
  kind: "unknown";
  originalType: string;
  raw: Record<string, unknown>;
}

export interface ParseResult {
  events: ParsedSessionEvent[];
  malformedLines: number;
  /** Index (in `events`) of the last fully parsed line — useful for incremental offset tracking. */
  lastValidLineIndex: number;
}

export function parseSessionJsonl(content: string): ParseResult {
  if (!content) return { events: [], malformedLines: 0, lastValidLineIndex: -1 };
  const lines = content.split("\n");
  const events: ParsedSessionEvent[] = [];
  let malformed = 0;
  let lastValid = -1;
  for (const line of lines) {
    if (!line) continue;
    let raw: Record<string, unknown>;
    try {
      raw = JSON.parse(line) as Record<string, unknown>;
    } catch {
      malformed++;
      continue;
    }
    events.push(parseOne(raw));
    lastValid = events.length - 1;
  }
  return { events, malformedLines: malformed, lastValidLineIndex: lastValid };
}

function parseOne(raw: Record<string, unknown>): ParsedSessionEvent {
  const base: BaseSessionEvent = {
    sessionId: typeof raw.sessionId === "string" ? raw.sessionId : undefined,
    timestamp: typeof raw.timestamp === "string" ? raw.timestamp : undefined,
    uuid: typeof raw.uuid === "string" ? raw.uuid : undefined,
    parentUuid:
      typeof raw.parentUuid === "string" || raw.parentUuid === null
        ? (raw.parentUuid as string | null)
        : undefined,
  };
  const type = typeof raw.type === "string" ? raw.type : "";
  switch (type) {
    case "user":
      return {
        ...base,
        kind: "user",
        content: (raw.message as { content?: unknown } | undefined)?.content ?? raw.message,
      };
    case "assistant": {
      const msg = raw.message as { content?: unknown; model?: unknown } | undefined;
      return {
        ...base,
        kind: "assistant",
        content: msg?.content ?? raw.message,
        model: typeof msg?.model === "string" ? msg.model : undefined,
      };
    }
    case "attachment":
      return { ...base, kind: "attachment", attachment: raw.attachment };
    case "queue-operation":
      return {
        ...base,
        kind: "queue-operation",
        operation: typeof raw.operation === "string" ? raw.operation : "unknown",
        detail: raw.content,
      };
    case "file-history-snapshot":
      return {
        ...base,
        kind: "file-history-snapshot",
        snapshot: raw.snapshot,
        isSnapshotUpdate: Boolean(raw.isSnapshotUpdate),
      };
    case "ai-title":
      return {
        ...base,
        kind: "ai-title",
        title:
          typeof (raw as { title?: unknown }).title === "string"
            ? (raw as { title: string }).title
            : "",
      };
    case "last-prompt":
      return { ...base, kind: "last-prompt", prompt: raw.prompt };
    case "system": {
      const content = typeof raw.content === "string" ? raw.content : "";
      const text = content || (typeof (raw as { text?: unknown }).text === "string" ? ((raw as { text: string }).text) : "");
      return {
        ...base,
        kind: "system",
        text,
        subtype: typeof raw.subtype === "string" ? raw.subtype : undefined,
      };
    }
    case "custom-title": {
      const title =
        typeof (raw as { customTitle?: unknown }).customTitle === "string"
          ? ((raw as { customTitle: string }).customTitle)
          : typeof (raw as { title?: unknown }).title === "string"
          ? ((raw as { title: string }).title)
          : "";
      return { ...base, kind: "custom-title", title };
    }
    case "agent-name": {
      const name =
        typeof (raw as { agentName?: unknown }).agentName === "string"
          ? ((raw as { agentName: string }).agentName)
          : typeof (raw as { name?: unknown }).name === "string"
          ? ((raw as { name: string }).name)
          : "";
      return { ...base, kind: "agent-name", name };
    }
    case "permission-mode": {
      const mode =
        typeof (raw as { permissionMode?: unknown }).permissionMode === "string"
          ? ((raw as { permissionMode: string }).permissionMode)
          : typeof (raw as { mode?: unknown }).mode === "string"
          ? ((raw as { mode: string }).mode)
          : "";
      return { ...base, kind: "permission-mode", mode };
    }
    default:
      return { ...base, kind: "unknown", originalType: type || "(no-type)", raw };
  }
}

// ---------- tool-use helpers (for inbox-derive) ----------

export interface ToolUseBlock {
  id: string;
  name: string;
  input: unknown;
  /** Index into the parsed events array of the assistant message that carried it. */
  atAssistantEvent: number;
}

export interface ToolResultBlock {
  toolUseId: string;
  atUserEvent: number;
}

export function extractToolUses(events: ParsedSessionEvent[]): ToolUseBlock[] {
  const out: ToolUseBlock[] = [];
  events.forEach((e, idx) => {
    if (e.kind !== "assistant") return;
    const content = e.content;
    if (!Array.isArray(content)) return;
    for (const block of content) {
      if (block && typeof block === "object") {
        const b = block as { type?: unknown; id?: unknown; name?: unknown; input?: unknown };
        if (
          b.type === "tool_use" &&
          typeof b.id === "string" &&
          typeof b.name === "string"
        ) {
          out.push({ id: b.id, name: b.name, input: b.input, atAssistantEvent: idx });
        }
      }
    }
  });
  return out;
}

export function extractToolResults(events: ParsedSessionEvent[]): ToolResultBlock[] {
  const out: ToolResultBlock[] = [];
  events.forEach((e, idx) => {
    if (e.kind !== "user") return;
    const content = e.content;
    if (!Array.isArray(content)) return;
    for (const block of content) {
      if (block && typeof block === "object") {
        const b = block as { type?: unknown; tool_use_id?: unknown };
        if (b.type === "tool_result" && typeof b.tool_use_id === "string") {
          out.push({ toolUseId: b.tool_use_id, atUserEvent: idx });
        }
      }
    }
  });
  return out;
}
