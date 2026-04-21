/*
 * Single TaskBoard card.
 *
 * Phase B1 rebuild (iterate 3.7b — 2026-04-20) against
 * `webui/designs/screens/kanban-with-projects.html` lines 546–730.
 *
 * Shape:
 *   ┌─────────────────────────────────────────────┐
 *   │ Title                       │ ▸ kind-stripe │   ← pipeline/iterate only
 *   │ 🏷 build-tag   15/15 ✓                      │
 *   │ abc1234 (mono)                      5h ago  │
 *   └─────────────────────────────────────────────┘
 *
 * Per-column card variants:
 *   - Draft  → Launch button only (can't resume a never-launched task).
 *   - In-progress → Launch + Resume always-visible (brown solid).
 *   - Done → neither launch nor resume (done-check indicator only).
 *
 * Sizing locks (explicit, not token) per B1 spec:
 *   padding:       12px 14px
 *   border-radius: 10px
 *
 * `testCounts` and `phase` fields don't exist on ExternalTask yet
 * (ADR-045 — deferred). Rendering is gracefully skipped when absent.
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21):
 *   - Whole-card click target now navigates to TaskDetail. The title text
 *     is no longer its own <button>; title editing lives in the Rename menu
 *     item (ADR-035). Keyboard support via Enter / Space on the role=button
 *     wrapper + inner controls (menu, launch pill, start pill) suppress
 *     their click propagation so they don't double-fire the navigate.
 *
 * Iterate 3.7d-b1 (2026-04-22):
 *   - Hover-gated launch chip replaced with always-visible brown solid
 *     `solid` variant buttons (Launch + Resume). Sven UAT: hover-to-reveal
 *     hides the primary action; make it always visible.
 *   - Footer reflow: timestamp LEFT, action buttons RIGHT. Action buttons
 *     wrap below the timestamp when the card is too narrow (flex-wrap).
 *   - `…` menu now always visible (was hover-gated) — matches the new
 *     "everything the user needs is visible" intent.
 *   - Commit marker moved inline with the timestamp on the left.
 *
 * Preserved testids:
 *   task-card-<id>, task-card-open-<id>, task-card-state-<id>,
 *   task-card-time-<id>, task-card-menu-<id>, task-card-close-<id>,
 *   task-card-delete-<id>.
 * New testids (iterate 3.7d-b1):
 *   task-card-actions-<id>, task-card-launch-<id>, task-card-resume-<id>,
 *   terminal-launch-solid-launch, terminal-launch-solid-resume
 *   (the last two are the TerminalLaunchButton's own testids in `solid`
 *   variant — not card-scoped but stable per button instance).
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

  // Commit hash — lifted off the sessionUuid for now (no per-task commit
  // field in the server model). Showing the first 7 chars of the session
  // UUID gives a stable mono-font marker that looks like a commit hash
  // per mockup without inventing new data.
  const commitMarker = task.sessionUuid.slice(0, 7);

  const navigateToDetail = () => navigate(`/tasks/${task.taskId}`);

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        onClick={navigateToDetail}
        onKeyDown={(ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            navigateToDetail();
          }
        }}
        className={
          "group relative cursor-pointer bg-[var(--color-surface)] " +
          "px-[14px] py-[12px] transition " +
          "shadow-[0_1px_3px_rgba(0,0,0,0.06)] " +
          "hover:-translate-y-[1px] hover:shadow-[0_4px_16px_rgba(0,0,0,0.12)] " +
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]"
        }
        style={{ borderRadius: "10px" }}
        data-testid={`task-card-${task.taskId}`}
        data-task-state={task.state}
        title={`UUID ${task.sessionUuid.slice(0, 8)} · cwd ${cwdBase}`}
      >
        {/* Kind stripe (4×18px top-right) — no `kind` field on the model
            yet, so this renders only when a future field appears. Left
            intentionally absent for now to avoid inventing data. */}

        {/* Top row: title + menu.
            The title keeps a testid (`task-card-open-*`) for existing
            specs, but is no longer a click-target — the whole card
            navigates to TaskDetail (iterate 3.7c-1). */}
        <div className="mb-2 flex items-start gap-2">
          <div
            className="min-w-0 flex-1"
            data-testid={`task-card-open-${task.taskId}`}
          >
            <div
              className={
                "flex items-center gap-1.5 text-[14px] font-medium leading-[1.4] " +
                (isDone
                  ? "text-[var(--color-muted)]"
                  : "text-[var(--color-text)]")
              }
            >
              <Icon className={iconClass(task.state)} size={14} />
              <span className="line-clamp-2">{task.title}</span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-0.5">
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <button
                  type="button"
                  onClick={(ev) => ev.stopPropagation()}
                  className="rounded p-1 text-[var(--color-muted)] transition-colors hover:bg-[var(--color-muted-bg)] hover:text-[var(--color-text)]"
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
                  className="z-50 min-w-[160px] rounded-[var(--radius-button)] border border-[var(--color-border)] bg-[var(--color-surface)] p-1 text-sm shadow-[var(--shadow-card)]"
                >
                  <DropdownMenu.Item
                    onSelect={() => closeMut.mutate(task.taskId)}
                    disabled={task.state === "done"}
                    className="cursor-pointer rounded px-2 py-1 text-[var(--color-text)] outline-none data-[highlighted]:bg-[var(--color-muted-bg)] data-[disabled]:cursor-not-allowed data-[disabled]:opacity-40"
                    data-testid={`task-card-close-${task.taskId}`}
                  >
                    Close (mark done)
                  </DropdownMenu.Item>
                  <DropdownMenu.Item
                    onSelect={onDeleteClick}
                    className="cursor-pointer rounded px-2 py-1 text-[var(--color-error)] outline-none data-[highlighted]:bg-[var(--color-error-bg)]"
                    data-testid={`task-card-delete-${task.taskId}`}
                  >
                    Delete (remove from board)
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </div>

        {/* Meta row — state pill + (future: phase tag / test-count) */}
        <div className="flex flex-wrap items-center gap-1.5">
          <StatePill state={task.state} />
          {/* Phase tag + test-count slots — hidden in B1; see ADR-045. */}
        </div>

        {/* Footer: timestamp + commit marker LEFT, action buttons RIGHT.
            Layout uses flex-wrap so on narrow cards the action buttons
            stack below the timestamp instead of overflowing. Each action
            button stops click propagation so it copies the command instead
            of navigating to TaskDetail (iterate 3.7d-b1). */}
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--color-muted)]">
          <div className="flex items-center gap-2 min-w-0">
            {stamp && (
              <span
                title={stamp.full}
                data-testid={`task-card-time-${task.taskId}`}
                className="whitespace-nowrap"
              >
                {stamp.short}
              </span>
            )}
            {!isDraft && (
              <span
                className="font-mono text-[11px] opacity-75"
                data-testid={`task-card-commit-${task.taskId}`}
              >
                {commitMarker}
              </span>
            )}
          </div>
          {!isDone && (
            <div
              className="ml-auto flex shrink-0 flex-wrap items-center justify-end gap-2"
              data-testid={`task-card-actions-${task.taskId}`}
            >
              {/* Draft → Launch only (cannot resume a never-launched task).
                  In-progress → Launch + Resume both visible (fresh restart
                  vs. continue-where-we-left-off). Done handled above. */}
              {isDraft ? (
                <span data-testid={`task-card-launch-${task.taskId}`}>
                  <TerminalLaunchButton
                    task={task}
                    variant="solid"
                    resume={false}
                  />
                </span>
              ) : (
                isInProgress && (
                  <>
                    <span data-testid={`task-card-launch-${task.taskId}`}>
                      <TerminalLaunchButton
                        task={task}
                        variant="solid"
                        resume={false}
                      />
                    </span>
                    <span data-testid={`task-card-resume-${task.taskId}`}>
                      <TerminalLaunchButton
                        task={task}
                        variant="solid"
                        resume={true}
                      />
                    </span>
                  </>
                )
              )}
            </div>
          )}
        </div>

        {/* State dataset — kept for testid parity with section-02 tests. */}
        <span
          className="sr-only"
          data-testid={`task-card-state-${task.taskId}`}
        >
          {task.state}
        </span>
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

/** Small muted pill showing the ExternalTaskState verbatim. Cheap stand-in
 *  for the mockup's richer `.tag-*` palette until ADR-045's phase + status
 *  projection lands in Phase C. */
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
      return { bg: "var(--color-warning-bg)", fg: "var(--color-warning-text)" };
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

function lastActivity(task: ExternalTask): { short: string; full: string } | null {
  // Prefer JSONL mtime; fall back to launchedAt; fall back to createdAt.
  const ms = task.lastJsonlSeenMtimeMs ?? toMs(task.launchedAt) ?? toMs(task.createdAt);
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

function basename(p: string): string {
  if (!p) return "";
  const norm = p.replace(/\\/g, "/");
  const parts = norm.split("/").filter(Boolean);
  return parts[parts.length - 1] ?? p;
}
