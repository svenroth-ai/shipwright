/*
 * POC vertical slice — client-side session JSONL parser.
 *
 * Parses the on-disk ~/.claude/projects/<cwd>/<uuid>.jsonl stream into
 * typed events suitable for read-only rendering. Unknown top-level
 * types fall through to an `unknown` variant so nothing is silently
 * dropped (round-1 GPT BLOCKER on transcript fallback).
 *
 * Observed top-level `type` values in the on-disk format (from PoC
 * fixtures 01/02/03/05): user, assistant, attachment, queue-operation,
 * file-history-snapshot, ai-title, last-prompt. More may surface for
 * plan-mode, slash commands, plugin events — the `unknown` variant
 * catches everything else.
 */

export type ParsedEvent =
  | UserEvent
  | AssistantEvent
  | AttachmentEvent
  | QueueOpEvent
  | FileSnapshotEvent
  | AiTitleEvent
  | LastPromptEvent
  | UnknownEvent;

export interface BaseEvent {
  sessionId?: string;
  timestamp?: string;
  uuid?: string;
}

export interface UserEvent extends BaseEvent {
  kind: "user";
  /** Raw message content as produced by the CLI. Could be string or block array. */
  content: unknown;
}

export interface AssistantEvent extends BaseEvent {
  kind: "assistant";
  /** Raw content array: text blocks, tool_use blocks, thinking, etc. */
  content: unknown;
}

export interface AttachmentEvent extends BaseEvent {
  kind: "attachment";
  /** Raw attachment payload. */
  attachment: unknown;
}

export interface QueueOpEvent extends BaseEvent {
  kind: "queue-operation";
  operation: string;
  detail?: unknown;
}

export interface FileSnapshotEvent extends BaseEvent {
  kind: "file-history-snapshot";
  snapshot: unknown;
  isSnapshotUpdate?: boolean;
}

export interface AiTitleEvent extends BaseEvent {
  kind: "ai-title";
  title: string;
}

export interface LastPromptEvent extends BaseEvent {
  kind: "last-prompt";
  prompt: unknown;
}

export interface UnknownEvent extends BaseEvent {
  kind: "unknown";
  /** Original top-level `type` string, if any. */
  originalType: string;
  /** Untouched raw event JSON for debugging / expand-to-raw rendering. */
  raw: Record<string, unknown>;
}

export interface ParseResult {
  events: ParsedEvent[];
  /** Lines that failed JSON.parse — typically the trailing partial line. */
  malformedLines: number;
}

export function parseSessionJsonl(content: string): ParseResult {
  if (!content) return { events: [], malformedLines: 0 };
  const lines = content.split("\n");
  const events: ParsedEvent[] = [];
  let malformed = 0;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    let raw: Record<string, unknown>;
    try {
      raw = JSON.parse(line) as Record<string, unknown>;
    } catch {
      // Last line of an actively-written file may be a torn read (the
      // newline hasn't been flushed yet). Silently swallow that case.
      // Middle-line parse failures point at real malformation or schema
      // drift — emit an unknown stub with the raw text so the UI can
      // show "skipped: bad JSON" instead of dropping silently.
      malformed++;
      const isLastLine = i === lines.length - 1;
      if (!isLastLine) {
        events.push({
          kind: "unknown",
          originalType: "(unparseable)",
          raw: { __rawLine: line.length > 500 ? `${line.slice(0, 500)}…` : line },
        });
      }
      continue;
    }
    events.push(parseOne(raw));
  }
  return { events, malformedLines: malformed };
}

function parseOne(raw: Record<string, unknown>): ParsedEvent {
  const base: BaseEvent = {
    sessionId: typeof raw.sessionId === "string" ? raw.sessionId : undefined,
    timestamp: typeof raw.timestamp === "string" ? raw.timestamp : undefined,
    uuid: typeof raw.uuid === "string" ? raw.uuid : undefined,
  };
  const type = typeof raw.type === "string" ? raw.type : "";
  switch (type) {
    case "user":
      return {
        ...base,
        kind: "user",
        content: (raw.message as { content?: unknown } | undefined)?.content ?? raw.message,
      };
    case "assistant":
      return {
        ...base,
        kind: "assistant",
        content: (raw.message as { content?: unknown } | undefined)?.content ?? raw.message,
      };
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
            ? ((raw as { title: string }).title)
            : "",
      };
    case "last-prompt":
      return { ...base, kind: "last-prompt", prompt: raw.prompt };
    default:
      return { ...base, kind: "unknown", originalType: type || "(no-type)", raw };
  }
}

/** Collapses an assistant event's content array into plain text for a minimal viewer. */
export function assistantText(e: AssistantEvent): string {
  const content = e.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const block of content) {
    if (block && typeof block === "object") {
      const b = block as { type?: unknown; text?: unknown };
      if (b.type === "text" && typeof b.text === "string") parts.push(b.text);
    }
  }
  return parts.join("\n");
}

/** Extracts user message text. User content can be string OR array OR object with content. */
export function userText(e: UserEvent): string {
  const c = e.content;
  if (typeof c === "string") return c;
  if (Array.isArray(c)) {
    const parts: string[] = [];
    for (const block of c) {
      if (block && typeof block === "object") {
        const b = block as { type?: unknown; text?: unknown; content?: unknown };
        if (b.type === "text" && typeof b.text === "string") parts.push(b.text);
        else if (b.type === "tool_result" && typeof b.content === "string") parts.push(`[tool_result] ${b.content}`);
      }
    }
    return parts.join("\n");
  }
  if (c && typeof c === "object") {
    const obj = c as { content?: unknown };
    if (typeof obj.content === "string") return obj.content;
  }
  return "";
}

/** Extracts tool_use blocks from an assistant event for a minimal tool-card list. */
export function toolUses(e: AssistantEvent): Array<{ id: string; name: string; input: unknown }> {
  const content = e.content;
  if (!Array.isArray(content)) return [];
  const out: Array<{ id: string; name: string; input: unknown }> = [];
  for (const block of content) {
    if (block && typeof block === "object") {
      const b = block as { type?: unknown; id?: unknown; name?: unknown; input?: unknown };
      if (b.type === "tool_use" && typeof b.id === "string" && typeof b.name === "string") {
        out.push({ id: b.id, name: b.name, input: b.input });
      }
    }
  }
  return out;
}

/**
 * Safe getter for AskUserQuestion's first question + options. Tolerates
 * shape drift (missing parts, malformed input, non-array options) — the
 * UI shows a generic fallback rather than crashing the transcript view.
 *
 * Observed shape: { input: { parts: [{ question: string, options: string[] }] } }.
 * The fallback covers the case where Claude or a plugin emits a
 * differently-named field (e.g. `query`, `prompt`).
 */
export function askUserQuestionSummary(input: unknown): {
  question: string;
  options: string[];
  fallback: boolean;
} {
  if (!input || typeof input !== "object") {
    return { question: "Question format unreadable", options: [], fallback: true };
  }
  const i = input as { parts?: unknown };
  if (!Array.isArray(i.parts) || i.parts.length === 0) {
    return { question: "Question format unreadable", options: [], fallback: true };
  }
  const first = i.parts[0];
  if (!first || typeof first !== "object") {
    return { question: "Question format unreadable", options: [], fallback: true };
  }
  const f = first as { question?: unknown; options?: unknown };
  const question = typeof f.question === "string" && f.question.trim()
    ? f.question
    : "Question format unreadable";
  const options = Array.isArray(f.options)
    ? f.options.filter((o): o is string => typeof o === "string")
    : [];
  return { question, options, fallback: question === "Question format unreadable" };
}

/** Extracts tool_result blocks from a user event (Claude reports tool
 * outputs as user-role events with `tool_result` content blocks). */
export function toolResults(
  e: UserEvent,
): Array<{ tool_use_id: string; content: string; is_error: boolean }> {
  const c = e.content;
  if (!Array.isArray(c)) return [];
  const out: Array<{ tool_use_id: string; content: string; is_error: boolean }> = [];
  for (const block of c) {
    if (block && typeof block === "object") {
      const b = block as {
        type?: unknown;
        tool_use_id?: unknown;
        content?: unknown;
        is_error?: unknown;
      };
      if (b.type === "tool_result" && typeof b.tool_use_id === "string") {
        const content = typeof b.content === "string"
          ? b.content
          : Array.isArray(b.content)
          ? collectTextBlocks(b.content)
          : "";
        out.push({
          tool_use_id: b.tool_use_id,
          content,
          is_error: Boolean(b.is_error),
        });
      }
    }
  }
  return out;
}

function collectTextBlocks(blocks: unknown[]): string {
  const parts: string[] = [];
  for (const block of blocks) {
    if (block && typeof block === "object") {
      const b = block as { type?: unknown; text?: unknown };
      if (b.type === "text" && typeof b.text === "string") parts.push(b.text);
    }
  }
  return parts.join("\n");
}
