/*
 * TaskListCard — 2026-04-23 iterate-20260423-task-list-unified / ADR-057.
 *
 * Unified task-list renderer that dispatches for THREE Claude tool_use
 * flavors:
 *   - TodoWrite — `input.todos` carries the full list per-call.
 *   - TaskCreate + TaskUpdate — incremental operations; list derived by
 *     walking events up to (and including) the current event's
 *     tool_use_id. Each event produces a snapshot of the accumulated
 *     state AT THAT MOMENT — same bubble shape, fresh state per call,
 *     matches the VS Code Claude Code extension's rendering pattern.
 *
 * Visual style mirrors VS Code:
 *   - Dark anthracite card
 *   - Header row with green bullet + bold "Update Todos" label
 *   - Body list: `✓ completed` (strike-through, muted) / `✱ in_progress`
 *     (bold, accent) / `☐ pending` (muted, not struck)
 *
 * Streaming tolerance (inherited from TodoWriteCard / ADR-056 FU-D):
 *   - Empty / partial input renders empty-list with a `…` progress
 *     indicator; does not flicker back to generic ToolCard mid-stream.
 *   - Fallback to generic ToolCard ONLY when the stream is complete
 *     AND the input shape is decisively invalid (non-object for
 *     TodoWrite; missing required fields for TaskCreate/TaskUpdate).
 */

import { Asterisk, Check, Square } from "lucide-react";
import { ToolCard } from "./ToolCard";

export type TaskStatus = "pending" | "in_progress" | "completed";

export interface TaskListItem {
  id: string;
  subject: string;
  status: string; // validated at render time; unknown → pending + drift subtitle
  activeForm?: string;
}

const KNOWN_STATUSES: ReadonlySet<string> = new Set([
  "pending",
  "in_progress",
  "completed",
]);

interface TaskListCardShellProps {
  tasks: TaskListItem[];
  /** Header label — defaults to "Update Todos" per VS Code convention. */
  headerLabel?: string;
  /** data-testid on the outer card. */
  testId?: string;
  /** Optional data-* attribute for the owning tool_use id. */
  toolUseId?: string;
}

/**
 * Pure render shell. Callers derive the `tasks` array from whatever
 * source they have (input.todos for TodoWrite, aggregated state for
 * TaskCreate/TaskUpdate).
 */
export function TaskListCardShell({
  tasks,
  headerLabel = "Update Todos",
  testId = "task-list-card",
  toolUseId,
}: TaskListCardShellProps) {
  const total = tasks.length;
  const completed = tasks.filter((t) => t.status === "completed").length;
  const isLoading = total === 0;

  return (
    <div
      className="max-w-[90%] w-full overflow-hidden"
      style={{
        background: "#1f2937",
        color: "#e5e7eb",
        border: "1px solid #374151",
        borderRadius: "var(--radius-button, 8px)",
        boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
      }}
      data-testid={testId}
      data-tool-use-id={toolUseId}
    >
      {/* Header — green bullet + bold "Update Todos" + N/M. */}
      <div
        className="flex items-center gap-2.5 px-3.5 py-2"
        style={{
          minHeight: 36,
          borderBottom: total > 0 ? "1px solid #374151" : "none",
        }}
      >
        <span
          className="inline-block shrink-0"
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "#10b981",
          }}
          aria-hidden="true"
        />
        <span
          className="flex-1 min-w-0 text-[13px] truncate"
          style={{ color: "#f3f4f6", fontWeight: 600 }}
          data-testid="task-list-card-title"
        >
          {headerLabel}
        </span>
        <span
          className="shrink-0 text-[11px] tabular-nums"
          style={{ color: "#9ca3af", fontWeight: 500 }}
          data-testid="task-list-card-progress"
        >
          {isLoading ? "…" : `${completed}/${total}`}
        </span>
      </div>
      {total > 0 && (
        <ol
          className="px-3.5 py-2.5"
          style={{ listStyle: "none", margin: 0, padding: "10px 14px" }}
          data-testid="task-list-card-list"
        >
          {tasks.map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
        </ol>
      )}
    </div>
  );
}

function TaskRow({ task }: { task: TaskListItem }) {
  const isKnown = KNOWN_STATUSES.has(task.status);
  const effective: TaskStatus = isKnown ? (task.status as TaskStatus) : "pending";
  const { Icon, iconColor, textColor, strike, weight } = statusStyle(effective);
  const displayText =
    effective === "in_progress" && task.activeForm && task.activeForm.trim().length > 0
      ? task.activeForm
      : task.subject;

  return (
    <li
      className="flex items-start gap-2.5 py-0.5 text-[13px]"
      data-testid="task-list-card-item"
      data-status={effective}
    >
      <span className="mt-0.5 shrink-0" style={{ color: iconColor }}>
        <Icon size={14} aria-hidden="true" />
      </span>
      <span
        className="flex-1 min-w-0"
        style={{
          color: textColor,
          textDecoration: strike ? "line-through" : "none",
          fontWeight: weight,
        }}
      >
        {displayText}
      </span>
      {!isKnown && (
        <span
          className="shrink-0 text-[10px] italic"
          style={{ color: "#6b7280" }}
          data-testid="task-list-card-unknown-status"
        >
          (unknown: {task.status})
        </span>
      )}
    </li>
  );
}

function statusStyle(status: TaskStatus): {
  Icon: typeof Square;
  iconColor: string;
  textColor: string;
  strike: boolean;
  weight: number;
} {
  switch (status) {
    case "completed":
      return {
        Icon: Check,
        iconColor: "#6b7280",
        textColor: "#6b7280",
        strike: true,
        weight: 400,
      };
    case "in_progress":
      return {
        Icon: Asterisk,
        iconColor: "#10b981",
        textColor: "#f3f4f6",
        strike: false,
        weight: 500,
      };
    case "pending":
    default:
      return {
        Icon: Square,
        iconColor: "#6b7280",
        textColor: "#d1d5db",
        strike: false,
        weight: 400,
      };
  }
}

// ── TodoWrite adapter ─────────────────────────────────────────────
// TodoWrite.input = { todos: [{ content, status, activeForm }] }
// Direct mapping to TaskListItem; no aggregation needed.

interface TodoWriteCardProps {
  id: string;
  input: unknown;
  result?: { content: string; is_error: boolean };
}

export function TodoWriteCard({ id, input, result }: TodoWriteCardProps) {
  const streamComplete = result != null;
  const tasks = parseTodoWriteInput(input, streamComplete);
  if (tasks === null) {
    return <ToolCard id={id} name="TodoWrite" input={input} result={result} />;
  }
  return (
    <TaskListCardShell
      tasks={tasks}
      headerLabel="Update Todos"
      testId="todo-write-card"
      toolUseId={id}
    />
  );
}

function parseTodoWriteInput(input: unknown, streamComplete: boolean): TaskListItem[] | null {
  if (input == null) return streamComplete ? null : [];
  if (typeof input !== "object" || Array.isArray(input)) {
    return streamComplete ? null : [];
  }
  const todosField = (input as { todos?: unknown }).todos;
  if (todosField == null) return streamComplete ? null : [];
  if (!Array.isArray(todosField)) return streamComplete ? null : [];
  const out: TaskListItem[] = [];
  for (let i = 0; i < todosField.length; i++) {
    const item = todosField[i];
    if (!item || typeof item !== "object") continue;
    const obj = item as { content?: unknown; status?: unknown; activeForm?: unknown };
    if (typeof obj.content !== "string" || obj.content.trim().length === 0) continue;
    out.push({
      id: String(i),
      subject: obj.content,
      status: typeof obj.status === "string" ? obj.status : "pending",
      activeForm: typeof obj.activeForm === "string" ? obj.activeForm : undefined,
    });
  }
  return out;
}

// ── TaskCreate + TaskUpdate aggregator ────────────────────────────
// TaskCreate.input = { subject, description, activeForm }  (no taskId;
//   Claude assigns implicit sequential IDs "1", "2", ...).
// TaskUpdate.input = { taskId: "N", status: "pending"|"in_progress"|"completed" }
//
// Build the list by walking ALL tool_use events (from the full filtered
// scope) in chronological order up to and INCLUDING the current event's
// tool_use_id, seeding from TaskCreate and flipping statuses on
// TaskUpdate. Produces the snapshot state AT THIS MOMENT.

export interface AggregatorToolUse {
  id: string;
  name: string;
  input: unknown;
}

/**
 * Derive task list state from a chronologically-ordered list of tool
 * uses (TaskCreate + TaskUpdate + others). Walks up to and INCLUDING
 * the event whose id === uptoToolUseId (when provided); otherwise
 * walks the full list.
 *
 * Returns the accumulated list of tasks at that point in time.
 */
export function deriveTaskListState(
  toolUses: AggregatorToolUse[],
  uptoToolUseId?: string,
): TaskListItem[] {
  const tasks = new Map<string, TaskListItem>();
  let createCounter = 0;
  for (const tu of toolUses) {
    if (tu.name === "TaskCreate") {
      createCounter += 1;
      const id = String(createCounter);
      const input = (tu.input ?? {}) as {
        subject?: unknown;
        activeForm?: unknown;
      };
      const subject =
        typeof input.subject === "string" && input.subject.trim().length > 0
          ? input.subject
          : `Task ${id}`;
      tasks.set(id, {
        id,
        subject,
        status: "pending",
        activeForm:
          typeof input.activeForm === "string" ? input.activeForm : undefined,
      });
    } else if (tu.name === "TaskUpdate") {
      const input = (tu.input ?? {}) as {
        taskId?: unknown;
        status?: unknown;
      };
      const taskId = typeof input.taskId === "string" ? input.taskId : undefined;
      const status = typeof input.status === "string" ? input.status : undefined;
      if (taskId && status) {
        const existing = tasks.get(taskId);
        if (existing) existing.status = status;
      }
    }
    if (uptoToolUseId && tu.id === uptoToolUseId) break;
  }
  return Array.from(tasks.values());
}

interface TaskListAggregateCardProps {
  id: string;
  /** Chronologically-ordered tool_uses across the full filtered scope. */
  allToolUses: AggregatorToolUse[];
  /** Whether the tool_result has arrived (stream complete). */
  streamComplete: boolean;
}

/**
 * Renderer for TaskCreate + TaskUpdate events. Aggregates state up to
 * this event's tool_use_id and renders the resulting snapshot.
 */
export function TaskListAggregateCard({
  id,
  allToolUses,
  streamComplete: _streamComplete,
}: TaskListAggregateCardProps) {
  const tasks = deriveTaskListState(allToolUses, id);
  return (
    <TaskListCardShell
      tasks={tasks}
      headerLabel="Update Todos"
      testId="task-list-card"
      toolUseId={id}
    />
  );
}
