/*
 * Compact List view for the TaskBoard.
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21). Minimal first pass:
 * one row per task, sorted by recency (lastJsonlSeenMtimeMs desc →
 * launchedAt → createdAt). Columns: title, state pill, commit marker,
 * timestamp, actions menu + launch pill. Matches the mockup intent
 * ("Board / List toggle") without rebuilding the entire kanban shell.
 *
 * Visual rules reuse the same warm-beige tokens as TaskCard — no new
 * tokens, no neutral or gray Tailwind utilities.
 *
 * Testids:
 *   task-list-view (wrapper), task-list-row-<id>, task-list-title-<id>,
 *   task-list-menu-<id>, task-list-close-<id>, task-list-delete-<id>.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
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

interface Props {
  tasks: ExternalTask[];
}

export function TaskList({ tasks }: Props) {
  const sorted = [...tasks].sort(byRecency);

  return (
    <div
      data-testid="task-list-view"
      className="flex flex-1 flex-col overflow-y-auto px-6 py-4"
    >
      <div
        className={
          "overflow-hidden rounded-[var(--radius-card)] " +
          "border border-[var(--color-border)] bg-[var(--color-surface)]"
        }
      >
        <div
          className={
            "grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 " +
            "border-b border-[var(--color-border)] bg-[var(--color-muted-bg)] " +
            "px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--color-muted)]"
          }
        >
          <span>Title</span>
          <span>State</span>
          <span className="hidden md:block">Commit</span>
          <span>Updated</span>
          <span className="sr-only">Actions</span>
        </div>
        {sorted.length === 0 ? (
          <div className="px-4 py-8 text-center text-[13px] text-[var(--color-muted)]">
            No tasks match the current filter.
          </div>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {sorted.map((t) => (
              <TaskListRow key={t.taskId} task={t} />
            ))}
          </ul>
        )}
      </div>
    </div>
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
      <li
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
          "grid grid-cols-[1fr_auto_auto_auto_auto] items-center gap-3 px-4 py-3 " +
          "text-[13px] transition-colors hover:bg-[var(--color-muted-bg)] " +
          "focus:outline-none focus-visible:bg-[var(--color-muted-bg)] cursor-pointer"
        }
        data-testid={`task-list-row-${task.taskId}`}
        data-task-state={task.state}
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
        <StatePill state={task.state} />
        <span
          className="hidden font-mono text-[11px] text-[var(--color-muted)] opacity-75 md:inline"
        >
          {isDraft ? "—" : commitMarker}
        </span>
        <span
          className="whitespace-nowrap text-[11px] text-[var(--color-muted)]"
          title={stamp?.full}
        >
          {stamp?.short ?? "—"}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {(isDraft || isInProgress) && (
            <span
              onClick={(ev) => ev.stopPropagation()}
              data-testid={`task-list-launch-${task.taskId}`}
            >
              <TerminalLaunchButton task={task} variant="compact" showLabel />
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
      </li>

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
  const ms =
    task.lastJsonlSeenMtimeMs ?? toMs(task.launchedAt) ?? toMs(task.createdAt);
  if (!ms) return null;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return null;
  const ago = relative(Date.now() - ms);
  return { short: ago, full: `${ago} (${d.toISOString()})` };
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

function byRecency(a: ExternalTask, b: ExternalTask): number {
  const am =
    a.lastJsonlSeenMtimeMs ?? toMs(a.launchedAt) ?? toMs(a.createdAt) ?? 0;
  const bm =
    b.lastJsonlSeenMtimeMs ?? toMs(b.launchedAt) ?? toMs(b.createdAt) ?? 0;
  return bm - am;
}
