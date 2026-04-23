/*
 * TodoWriteCard — 2026-04-23 iterate-20260423-chat-livetest-2 AC-D / ADR-056.
 *
 * Specialized renderer for `TodoWrite` tool_use blocks. Replaces the
 * generic ToolCard (which collapsed the input into a JSON blob) with a
 * checklist-with-progress card — the format that matches how users
 * actually consume Claude's own plan during a session.
 *
 * Shape of input (verified against real JSONL `toolu_016DGoLZh...`):
 *   input = {
 *     todos: [
 *       { content: string, status: "pending"|"in_progress"|"completed", activeForm: string },
 *       ...
 *     ]
 *   }
 *
 * Expanded by default (unlike generic ToolCard) — the list IS the
 * value, not a detail. Header shows the progress summary `N/M`.
 *
 * Streaming tolerance (Gemini external-review finding #1 HIGH):
 *   - `input` arrives incrementally during streaming. A partial
 *     `{ todos: null }` or `{}` must NOT flash back to ToolCard —
 *     render an empty checklist with a loading header instead.
 *   - Fallback to generic ToolCard ONLY when the tool_result has
 *     arrived (stream complete) AND the input shape is decisively
 *     invalid. While streaming, tolerate missing / partial fields.
 *
 * Runtime shape guards (GPT external-review finding #10):
 *   - `Array.isArray(todos)` before iterating.
 *   - Filter to object items only; skip malformed rows.
 *   - Use `activeForm || content` for `in_progress` items (Claude's
 *     convention for present-continuous display).
 *   - Progress `N/M` computed from the filtered-valid array — header
 *     count matches body row count (Gemini finding #3).
 *
 * Historical preservation: each TodoWrite tool_use is its own card.
 * A later tool_use with a refreshed list renders as ANOTHER card; old
 * cards stay with their snapshot state. Users can scroll back to see
 * "what the plan looked like at step 3."
 */

import { CircleDashed, ListChecks, Square, SquareCheck } from "lucide-react";
import { ToolCard } from "./ToolCard";

/**
 * Recognized todo statuses. Unknown values are rendered with a muted
 * "unknown status" subtitle for schema-drift discoverability.
 */
type TodoStatus = "pending" | "in_progress" | "completed";
const KNOWN_STATUSES: ReadonlySet<string> = new Set([
  "pending",
  "in_progress",
  "completed",
]);

interface TodoItem {
  content: string;
  status: string; // validated at render time
  activeForm?: string;
}

interface Props {
  id: string;
  name: string;
  input: unknown;
  result?: { content: string; is_error: boolean };
}

/**
 * Parse and validate the TodoWrite input shape tolerantly. Returns:
 *   - `{ todos: [...] }` when the shape is recognizable (possibly empty
 *     array during streaming).
 *   - `null` when the shape is decisively invalid and we should fall
 *     back to the generic ToolCard.
 *
 * Streaming rule: if `input` is a non-object, `null`, or an object
 * whose `todos` key is missing entirely, we return an empty `todos`
 * array (streaming in progress). Fallback to null happens ONLY when
 * `input` is clearly unrelated (e.g. a string, number, or has
 * non-array `todos` AFTER the tool_result arrives).
 */
function parseTodos(input: unknown, streamComplete: boolean): TodoItem[] | null {
  if (input == null) {
    return streamComplete ? null : [];
  }
  if (typeof input !== "object" || Array.isArray(input)) {
    return streamComplete ? null : [];
  }
  const todosField = (input as { todos?: unknown }).todos;
  if (todosField === undefined || todosField === null) {
    // No todos key yet — treat as streaming if stream incomplete.
    return streamComplete ? null : [];
  }
  if (!Array.isArray(todosField)) {
    return streamComplete ? null : [];
  }
  const out: TodoItem[] = [];
  for (const item of todosField) {
    if (!item || typeof item !== "object") continue;
    const obj = item as { content?: unknown; status?: unknown; activeForm?: unknown };
    if (typeof obj.content !== "string" || obj.content.trim().length === 0) continue;
    out.push({
      content: obj.content,
      status: typeof obj.status === "string" ? obj.status : "pending",
      activeForm: typeof obj.activeForm === "string" ? obj.activeForm : undefined,
    });
  }
  return out;
}

export function TodoWriteCard({ id, name, input, result }: Props) {
  const streamComplete = result != null;
  const todos = parseTodos(input, streamComplete);

  // Decisive fallback: stream complete AND input shape is garbage →
  // let generic ToolCard handle it (user still sees SOMETHING).
  if (todos === null) {
    return <ToolCard id={id} name={name} input={input} result={result} />;
  }

  const total = todos.length;
  const completed = todos.filter((t) => t.status === "completed").length;
  const isLoading = total === 0 && !streamComplete;

  return (
    <div
      className="max-w-[90%] w-full overflow-hidden"
      style={{
        background: "var(--color-surface, #ffffff)",
        border: "1px solid var(--color-border, #e0dbd4)",
        borderRadius: "var(--radius-button, 8px)",
        boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
      }}
      data-testid="todo-write-card"
      data-tool-use-id={id}
    >
      {/* Header — always visible, no collapse. */}
      <div
        className="flex items-center gap-2.5 px-3.5 py-2"
        style={{
          minHeight: 38,
          borderBottom: total > 0 ? "1px solid var(--color-border, #e0dbd4)" : "none",
        }}
      >
        <div
          className="flex items-center justify-center rounded-md shrink-0"
          style={{
            width: 22,
            height: 22,
            background: "var(--color-muted-bg, #ede8e1)",
            color: "var(--color-accent, #857568)",
          }}
        >
          <ListChecks size={12} aria-hidden="true" />
        </div>
        <span
          className="flex-1 min-w-0 font-mono text-[12.5px] truncate"
          style={{ color: "var(--color-text, #1a1a1a)", fontWeight: 500 }}
          data-testid="todo-write-card-title"
        >
          Todos
        </span>
        <span
          className="shrink-0 text-[11px] tabular-nums"
          style={{ color: "var(--color-muted, #6b7280)", fontWeight: 500 }}
          data-testid="todo-write-card-progress"
        >
          {isLoading ? "…" : `${completed}/${total}`}
        </span>
      </div>
      {/* Body — list of items. Skip entirely when loading / empty. */}
      {total > 0 && (
        <ol
          className="px-3.5 py-2"
          style={{ listStyle: "none", margin: 0, padding: "8px 14px" }}
          data-testid="todo-write-card-list"
        >
          {todos.map((item, i) => (
            <TodoRow key={i} item={item} />
          ))}
        </ol>
      )}
    </div>
  );
}

function TodoRow({ item }: { item: TodoItem }) {
  const status = item.status;
  const isKnown = KNOWN_STATUSES.has(status);
  const effectiveStatus: TodoStatus = isKnown ? (status as TodoStatus) : "pending";
  const { Icon, iconColor, textColor, strike } = statusStyle(effectiveStatus);

  // Present-continuous form for in-progress items when available
  // (GPT external-review #10 fallback — empty activeForm → content).
  const displayText =
    effectiveStatus === "in_progress" && item.activeForm && item.activeForm.trim().length > 0
      ? item.activeForm
      : item.content;

  return (
    <li
      className="flex items-start gap-2 py-1 text-[13px]"
      data-testid="todo-write-card-item"
      data-status={effectiveStatus}
    >
      <span className="mt-0.5 shrink-0" style={{ color: iconColor }}>
        <Icon size={14} aria-hidden="true" />
      </span>
      <span
        className="flex-1 min-w-0"
        style={{
          color: textColor,
          textDecoration: strike ? "line-through" : "none",
        }}
      >
        {displayText}
      </span>
      {!isKnown && (
        <span
          className="shrink-0 text-[10px] italic"
          style={{ color: "var(--color-muted, #6b7280)" }}
          data-testid="todo-write-card-unknown-status"
        >
          (unknown status: {status})
        </span>
      )}
    </li>
  );
}

function statusStyle(status: TodoStatus): {
  Icon: typeof Square;
  iconColor: string;
  textColor: string;
  strike: boolean;
} {
  switch (status) {
    case "completed":
      return {
        Icon: SquareCheck,
        iconColor: "var(--color-success, #059669)",
        textColor: "var(--color-muted, #6b7280)",
        strike: true,
      };
    case "in_progress":
      return {
        Icon: CircleDashed,
        iconColor: "var(--color-warning, #D97706)",
        textColor: "var(--color-text, #1a1a1a)",
        strike: false,
      };
    case "pending":
    default:
      return {
        Icon: Square,
        iconColor: "var(--color-muted, #6b7280)",
        textColor: "var(--color-text, #1a1a1a)",
        strike: false,
      };
  }
}
