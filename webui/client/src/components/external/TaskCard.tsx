/*
 * Single TaskBoard card.
 *
 * Replaces the inline rendering in TaskBoardPage with a richer card per
 * the iterate 2 plan:
 *   - State icon: Circle (draft), Loader (awaiting_external_start),
 *     Zap (active), PauseCircle (idle), AlertTriangle (jsonl_missing /
 *     launch_failed), CheckCircle2 (done).
 *   - Last-activity timestamp absolute HH:mm (tooltip = relative + ISO).
 *   - Hover popover: session UUID first 8 chars + cwd basename.
 *   - Compact <TerminalLaunchButton variant="compact" /> on the card.
 *   - Three-dots menu (Close + Delete) — confirm dialog for Delete on
 *     non-terminal states.
 *
 * Plan keeps tool actions narrow to Close / Delete; no Cancel.
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
import { useCloseExternalTask, useDeleteExternalTask } from "../../hooks/useExternalTasks";
import { TerminalLaunchButton } from "./TerminalLaunchButton";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";

const NONTERMINAL_STATES: ExternalTaskState[] = ["active", "idle", "awaiting_external_start"];

interface Props {
  task: ExternalTask;
}

export function TaskCard({ task }: Props) {
  const navigate = useNavigate();
  const closeMut = useCloseExternalTask();
  const deleteMut = useDeleteExternalTask();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const Icon = stateIcon(task.state);
  const stamp = lastActivity(task);
  const cwdBase = basename(task.cwd);

  const onDeleteClick = () => {
    if (NONTERMINAL_STATES.includes(task.state)) {
      setConfirmDelete(true);
    } else {
      deleteMut.mutate(task.taskId);
    }
  };

  return (
    <>
      <div
        className="group flex flex-col gap-1.5 rounded-lg border border-neutral-200 bg-white p-2.5 shadow-sm transition hover:border-blue-300 hover:shadow-md"
        data-testid={`task-card-${task.taskId}`}
        data-task-state={task.state}
        title={`UUID ${task.sessionUuid.slice(0, 8)} · cwd ${cwdBase}`}
      >
        <div className="flex items-start gap-2">
          <button
            type="button"
            onClick={() => navigate(`/tasks/${task.taskId}`)}
            className="min-w-0 flex-1 text-left"
            data-testid={`task-card-open-${task.taskId}`}
          >
            <div className="flex items-center gap-1.5 text-sm font-medium text-neutral-900">
              <Icon className={iconClass(task.state)} size={14} />
              <span className="truncate">{task.title}</span>
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-neutral-500">
              <span data-testid={`task-card-state-${task.taskId}`}>{task.state}</span>
              {stamp && (
                <span title={stamp.full} data-testid={`task-card-time-${task.taskId}`}>
                  · {stamp.short}
                </span>
              )}
              <span className="truncate font-mono text-neutral-400" title={task.cwd}>
                · {cwdBase}
              </span>
            </div>
          </button>

          <div className="flex shrink-0 items-center gap-0.5">
            <TerminalLaunchButton task={task} variant="compact" />

            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  className="rounded p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
                  aria-label="Task actions"
                  data-testid={`task-card-menu-${task.taskId}`}
                >
                  <MoreHorizontal size={14} />
                </button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  align="end"
                  sideOffset={4}
                  className="z-50 min-w-[160px] rounded-md border border-neutral-200 bg-white p-1 text-sm shadow-lg"
                >
                  <DropdownMenu.Item
                    onSelect={() => closeMut.mutate(task.taskId)}
                    disabled={task.state === "done"}
                    className="cursor-pointer rounded px-2 py-1 text-neutral-800 outline-none data-[highlighted]:bg-neutral-100 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40"
                    data-testid={`task-card-close-${task.taskId}`}
                  >
                    Close (mark done)
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={onDeleteClick}
                    className="cursor-pointer rounded px-2 py-1 text-red-700 outline-none data-[highlighted]:bg-red-50"
                    data-testid={`task-card-delete-${task.taskId}`}
                  >
                    Delete (remove from board)
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </div>
      </div>

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
      return "text-green-600";
    case "idle":
      return "text-neutral-400";
    case "awaiting_external_start":
      return "text-amber-600";
    case "jsonl_missing":
    case "launch_failed":
      return "text-red-600";
    case "done":
      return "text-green-700";
    case "draft":
    default:
      return "text-neutral-500";
  }
}

function lastActivity(task: ExternalTask): { short: string; full: string } | null {
  // Prefer JSONL mtime; fall back to launchedAt; fall back to createdAt.
  const ms = task.lastJsonlSeenMtimeMs ?? toMs(task.launchedAt) ?? toMs(task.createdAt);
  if (!ms) return null;
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return null;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ago = relative(Date.now() - ms);
  return { short: `${hh}:${mm}`, full: `${ago} (${d.toISOString()})` };
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

function basename(p: string): string {
  if (!p) return "";
  const norm = p.replace(/\\/g, "/");
  const parts = norm.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? p;
}
