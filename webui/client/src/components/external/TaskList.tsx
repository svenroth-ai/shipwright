/*
 * Table-backed List view for the TaskBoard.
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21): first pass was a
 * compact row list with a grid layout.
 *
 * Iterate 3.7d-b1 (2026-04-22) rebuild:
 *   - Proper semantic <table> with <thead>/<tbody>.
 *   - Columns: Title · State · Phase · Commit · Updated · Actions.
 *   - Sortable headers:
 *       - "Title"   → alphabetical toggle (asc/desc).
 *       - "Updated" → default; last-activity desc by default, toggle on click.
 *     The other headers are static labels (non-sortable for now — no obvious
 *     meaningful sort for State / Phase / Commit beyond bucket-grouping).
 *   - Full row click → TaskDetail. Actions column + menu stops propagation.
 *   - Phase column: no phase field on ExternalTask yet (ADR-045 — deferred);
 *     renders `—` until the phase projection lands.
 *   - Commit column: short sessionUuid slice as a stand-in for a future
 *     per-task commit field; draft tasks render `—` because a never-
 *     launched task has no meaningful commit to show.
 *
 * Tokens only from index.css; no neutral-* / gray-* utilities. Same visual
 * vocabulary as TaskCard so the two views feel like the same surface in
 * different layouts.
 *
 * Testids:
 *   task-list-view, task-list-table,
 *   task-list-header-<column>, task-list-row-<taskId>,
 *   task-list-cell-<taskId>-<column>,
 *   task-list-title-<id>, task-list-menu-<id>,
 *   task-list-close-<id>, task-list-delete-<id>,
 *   task-list-launch-<id>.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  Loader,
  MoreHorizontal,
  PauseCircle,
  Zap,
} from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import type { ExternalTask, ExternalTaskState } from "../../lib/externalApi";
import {
  useCloseExternalTask,
  useDeleteExternalTask,
} from "../../hooks/useExternalTasks";
import { TerminalLaunchButton } from "./TerminalLaunchButton";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";

const NONTERMINAL_STATES: ExternalTaskState[] = [
  "active",
  "idle",
  "awaiting_external_start",
];

type SortKey = "title" | "updated";
type SortDir = "asc" | "desc";

interface Props {
  tasks: ExternalTask[];
}

export function TaskList({ tasks }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    const arr = [...tasks];
    if (sortKey === "title") {
      arr.sort((a, b) =>
        (a.title ?? "").localeCompare(b.title ?? "", undefined, {
          sensitivity: "base",
        }),
      );
    } else {
      arr.sort((a, b) => lastActivityMs(a) - lastActivityMs(b));
    }
    if (sortDir === "desc") arr.reverse();
    return arr;
  }, [tasks, sortKey, sortDir]);

  function onHeaderClick(next: SortKey) {
    if (sortKey === next) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(next);
      setSortDir(next === "title" ? "asc" : "desc");
    }
  }

  return (
    <div
      data-testid="task-list-view"
      // iterate 3.7h (Sven UAT): drop the 1600-max inner container + outer
      // px-6 padding. Outer .page-container in TaskBoardPage now owns the
      // width + margins so the table aligns with the header + filter row.
      className="flex flex-1 flex-col"
    >
      <div
        className={
          "overflow-hidden rounded-[var(--radius-card)] " +
          "border border-[var(--color-border)] bg-[var(--color-surface)]"
        }
      >
        <table
          data-testid="task-list-table"
          className="w-full border-collapse text-left text-[13px]"
        >
          <thead>
            <tr
              className={
                "border-b border-[var(--color-border)] bg-[var(--color-muted-bg)] " +
                "text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--color-muted)]"
              }
            >
              <SortableTh
                col="title"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={onHeaderClick}
              >
                Title
              </SortableTh>
              <th
                data-testid="task-list-header-state"
                className="whitespace-nowrap px-4 py-2"
              >
                State
              </th>
              <th
                data-testid="task-list-header-phase"
                className="whitespace-nowrap px-4 py-2"
              >
                Phase
              </th>
              <th
                data-testid="task-list-header-commit"
                className="hidden whitespace-nowrap px-4 py-2 md:table-cell"
              >
                Commit
              </th>
              <SortableTh
                col="updated"
                sortKey={sortKey}
                sortDir={sortDir}
                onClick={onHeaderClick}
              >
                Updated
              </SortableTh>
              <th
                data-testid="task-list-header-actions"
                className="w-px whitespace-nowrap px-4 py-2 text-right"
              >
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-8 text-center text-[13px] text-[var(--color-muted)]"
                >
                  No tasks match the current filter.
                </td>
              </tr>
            ) : (
              sorted.map((t) => <TaskListRow key={t.taskId} task={t} />)
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface SortableThProps {
  col: SortKey;
  sortKey: SortKey;
  sortDir: SortDir;
  onClick: (next: SortKey) => void;
  children: React.ReactNode;
}

function SortableTh({
  col,
  sortKey,
  sortDir,
  onClick,
  children,
}: SortableThProps) {
  const active = sortKey === col;
  return (
    <th
      data-testid={`task-list-header-${col}`}
      data-sort-active={active || undefined}
      data-sort-dir={active ? sortDir : undefined}
      className="whitespace-nowrap px-4 py-2"
    >
      <button
        type="button"
        onClick={() => onClick(col)}
        className={
          "inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.04em] " +
          (active
            ? "text-[var(--color-text)]"
            : "text-[var(--color-muted)] hover:text-[var(--color-text)]")
        }
        aria-label={`Sort by ${String(children)} ${active && sortDir === "asc" ? "descending" : "ascending"}`}
      >
        <span>{children}</span>
        {active ? (
          sortDir === "asc" ? (
            <ChevronUp size={12} />
          ) : (
            <ChevronDown size={12} />
          )
        ) : (
          <ChevronDown size={12} className="opacity-40" />
        )}
      </button>
    </th>
  );
}

function TaskListRow({ task }: { task: ExternalTask }) {
  const navigate = useNavigate();
  const closeMut = useCloseExternalTask();
  const deleteMut = useDeleteExternalTask();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const Icon = stateIcon(task.state);
  const stamp = lastActivity(task);
  const commitMarker = task.sessionUuid.slice(0, 7);
  const isDraft = task.state === "draft";
  const isDone = task.state === "done";
  const isInProgress =
    task.state === "active" ||
    task.state === "idle" ||
    task.state === "awaiting_external_start";

  const onDeleteClick = () => {
    if (NONTERMINAL_STATES.includes(task.state)) {
      setConfirmDelete(true);
    } else {
      deleteMut.mutate(task.taskId);
    }
  };

  const go = () => navigate(`/tasks/${task.taskId}`);

  return (
    <>
      <tr
        role="button"
        tabIndex={0}
        onClick={go}
        onKeyDown={(ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            go();
          }
        }}
        className={
          "cursor-pointer border-t border-[var(--color-border)] " +
          "transition-colors hover:bg-[var(--color-muted-bg)] " +
          "focus:outline-none focus-visible:bg-[var(--color-muted-bg)]"
        }
        data-testid={`task-list-row-${task.taskId}`}
        data-task-state={task.state}
      >
        <td
          className="min-w-0 px-4 py-3"
          data-testid={`task-list-cell-${task.taskId}-title`}
        >
          <div className="flex min-w-0 items-center gap-2">
            <Icon className={iconClass(task.state)} size={14} />
            <span
              className={
                "truncate font-medium " +
                (isDone
                  ? "text-[var(--color-muted)]"
                  : "text-[var(--color-text)]")
              }
              data-testid={`task-list-title-${task.taskId}`}
            >
              {task.title}
            </span>
          </div>
        </td>
        <td
          className="whitespace-nowrap px-4 py-3"
          data-testid={`task-list-cell-${task.taskId}-state`}
        >
          <StatePill state={task.state} />
        </td>
        <td
          className="whitespace-nowrap px-4 py-3 text-[11px] text-[var(--color-muted)]"
          data-testid={`task-list-cell-${task.taskId}-phase`}
        >
          {/* ExternalTask has no `phase` field yet (ADR-045 — deferred).
              Render an em-dash placeholder so the table keeps a stable
              column width across states. */}
          —
        </td>
        <td
          className="hidden whitespace-nowrap px-4 py-3 font-mono text-[11px] text-[var(--color-muted)] opacity-75 md:table-cell"
          data-testid={`task-list-cell-${task.taskId}-commit`}
        >
          {isDraft ? "—" : commitMarker}
        </td>
        <td
          className="whitespace-nowrap px-4 py-3 text-[11px] text-[var(--color-muted)]"
          title={stamp?.full}
          data-testid={`task-list-cell-${task.taskId}-updated`}
        >
          {stamp?.short ?? "—"}
        </td>
        <td
          className="whitespace-nowrap px-4 py-3 text-right"
          data-testid={`task-list-cell-${task.taskId}-actions`}
          onClick={(ev) => ev.stopPropagation()}
          onKeyDown={(ev) => ev.stopPropagation()}
        >
          <div className="flex shrink-0 items-center justify-end gap-1">
            {(isDraft || isInProgress) && (
              <span data-testid={`task-list-launch-${task.taskId}`}>
                <TerminalLaunchButton
                  task={task}
                  variant="compact"
                  showLabel
                />
              </span>
            )}
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  onClick={(ev) => ev.stopPropagation()}
                  className="rounded p-1 text-[var(--color-muted)] hover:bg-[var(--color-muted-bg)] hover:text-[var(--color-text)]"
                  aria-label="Task actions"
                  data-testid={`task-list-menu-${task.taskId}`}
                >
                  <MoreHorizontal size={14} />
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={4}
                  className="z-50 min-w-[160px] rounded-[var(--radius-button)] border border-[var(--color-border)] bg-[var(--color-surface)] p-1 text-sm shadow-[var(--shadow-card)]"
                >
                  <DropdownMenu.Item
                    onSelect={() => closeMut.mutate(task.taskId)}
                    disabled={task.state === "done"}
                    className="cursor-pointer rounded px-2 py-1 text-[var(--color-text)] outline-none data-[highlighted]:bg-[var(--color-muted-bg)] data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40"
                    data-testid={`task-list-close-${task.taskId}`}
                  >
                    Close (mark done)
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={onDeleteClick}
                    className="cursor-pointer rounded px-2 py-1 text-[var(--color-error)] outline-none data-[highlighted]:bg-[var(--color-error-bg)]"
                    data-testid={`task-list-delete-${task.taskId}`}
                  >
                    Delete (remove from board)
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </td>
      </tr>

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        task={task}
        onConfirm={() => {
          deleteMut.mutate(task.taskId);
          setConfirmDelete(false);
        }}
      />
    </>
  );
}

function StatePill({ state }: { state: ExternalTaskState }) {
  const tone = statePillTone(state);
  return (
    <span
      className="inline-flex items-center gap-1 rounded-[10px] px-2 py-[2px] text-[11px] font-semibold"
      style={{ background: tone.bg, color: tone.fg }}
    >
      {state}
    </span>
  );
}

function statePillTone(state: ExternalTaskState): { bg: string; fg: string } {
  switch (state) {
    case "active":
    case "awaiting_external_start":
      return { bg: "var(--color-warning-bg)", fg: "var(--color-warning-text)" };
    case "idle":
      return { bg: "var(--color-muted-bg)", fg: "var(--color-muted)" };
    case "jsonl_missing":
    case "launch_failed":
      return { bg: "var(--color-error-bg)", fg: "var(--color-error)" };
    case "done":
      return { bg: "var(--color-info-bg)", fg: "#2563eb" };
    case "draft":
    default:
      return { bg: "var(--color-muted-bg)", fg: "var(--color-muted)" };
  }
}

function stateIcon(state: ExternalTaskState) {
  switch (state) {
    case "draft":
      return Circle;
    case "awaiting_external_start":
      return Loader;
    case "active":
      return Zap;
    case "idle":
      return PauseCircle;
    case "jsonl_missing":
    case "launch_failed":
      return AlertTriangle;
    case "done":
      return CheckCircle2;
  }
}

function iconClass(state: ExternalTaskState): string {
  switch (state) {
    case "active":
      return "text-[var(--color-success)]";
    case "idle":
      return "text-[var(--color-muted)]";
    case "awaiting_external_start":
      return "text-[var(--color-warning)]";
    case "jsonl_missing":
    case "launch_failed":
      return "text-[var(--color-error)]";
    case "done":
      return "text-[var(--color-success)]";
    case "draft":
    default:
      return "text-[var(--color-muted)]";
  }
}

function lastActivity(
  task: ExternalTask,
): { short: string; full: string } | null {
  const ms = lastActivityMs(task);
  if (!ms) return null;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return null;
  const ago = relative(Date.now() - ms);
  return { short: ago, full: `${ago} (${d.toISOString()})` };
}

function lastActivityMs(task: ExternalTask): number {
  return (
    task.lastJsonlSeenMtimeMs ??
    toMs(task.launchedAt) ??
    toMs(task.createdAt) ??
    0
  );
}

function toMs(iso: string | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : null;
}

function relative(deltaMs: number): string {
  if (deltaMs < 60_000) return "just now";
  if (deltaMs < 3_600_000) return `${Math.floor(deltaMs / 60_000)}m ago`;
  if (deltaMs < 86_400_000) return `${Math.floor(deltaMs / 3_600_000)}h ago`;
  return `${Math.floor(deltaMs / 86_400_000)}d ago`;
}
