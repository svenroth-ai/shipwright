/*
 * TaskDetailHeader — single header bar above the 3-pane body (iterate 3
 * section 04, FR-03.30).
 *
 * Owns:
 *   - state-dependent primary CTA:
 *       pending / draft / awaiting_external_start → "Launch in Terminal"
 *       active / idle                             → "Copy Resume Command"
 *       done / launch_failed / jsonl_missing      → no CTA
 *   - project chip popover (reassignment — ProjectChipMenu)
 *   - 3-dots menu with Close + Delete (+ debug SessionMetadata footer)
 *   - state badge, editable title, breadcrumb back link
 *
 * Regression guards:
 *   - NO chat composer anywhere (CLAUDE.md DO-NOT #3).
 *   - "Copy Resume Command" COPIES TO CLIPBOARD — never spawns Claude
 *     (DO-NOT #5).
 *   - Fork has moved to iterate 4 — menu must NOT surface it.
 */

import { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ChevronUp,
  Copy,
  MoreVertical,
  Rocket,
  Terminal as TerminalIcon,
  Trash2,
  X,
} from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import type {
  CopyCommandForms,
  ExternalTask,
} from "../../lib/externalApi";
import {
  useCloseExternalTask,
  useDeleteExternalTask,
} from "../../hooks/useExternalTasks";
import { useLaunchTask } from "../../hooks/useLaunchTask";
import { EditableTaskTitle } from "./EditableTaskTitle";
import { ProjectChipMenu } from "./ProjectChipMenu";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { SessionMetadata } from "./SessionMetadata";

const STATE_BADGE_STYLES: Record<ExternalTask["state"], string> = {
  draft: "bg-neutral-200 text-neutral-800",
  awaiting_external_start: "bg-amber-100 text-amber-900",
  active: "bg-emerald-100 text-emerald-900",
  idle: "bg-neutral-100 text-neutral-600",
  jsonl_missing: "bg-red-100 text-red-900",
  launch_failed: "bg-red-100 text-red-900",
  done: "bg-neutral-300 text-neutral-600",
};

type CtaMode = "launch" | "resume" | "none";

function ctaFor(state: ExternalTask["state"]): CtaMode {
  if (state === "draft" || state === "awaiting_external_start") return "launch";
  if (state === "active" || state === "idle") return "resume";
  return "none";
}

function isTerminalState(state: ExternalTask["state"]): boolean {
  return state === "done";
}

function pickPlatformCommand(commands: CopyCommandForms): string {
  if (typeof navigator === "undefined") return commands.posix;
  return /windows/i.test(navigator.userAgent) ? commands.powershell : commands.posix;
}

async function writeClipboard(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
  } finally {
    document.body.removeChild(ta);
  }
}

interface Props {
  task: ExternalTask;
}

export function TaskDetailHeader({ task }: Props) {
  const launchMut = useLaunchTask();
  const closeMut = useCloseExternalTask();
  const deleteMut = useDeleteExternalTask();

  const [copiedLabel, setCopiedLabel] = useState<string | null>(null);
  const [ctaError, setCtaError] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const copyResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cta = ctaFor(task.state);

  const flashCopied = useCallback((label: string) => {
    setCopiedLabel(label);
    if (copyResetTimer.current) clearTimeout(copyResetTimer.current);
    copyResetTimer.current = setTimeout(() => setCopiedLabel(null), 1800);
  }, []);

  const handleLaunch = useCallback(async () => {
    setCtaError(null);
    try {
      const { commands } = await launchMut.mutateAsync({
        taskId: task.taskId,
        resume: false,
      });
      const command = pickPlatformCommand(commands);
      await writeClipboard(command);
      flashCopied("Launch command copied");
    } catch (err) {
      setCtaError(err instanceof Error ? err.message : String(err));
    }
  }, [launchMut, task.taskId, flashCopied]);

  const handleResume = useCallback(async () => {
    setCtaError(null);
    try {
      // Request a resume command. `resume: true` produces a --resume <uuid>
      // command string in the server response — we COPY it to the
      // clipboard (never spawn), satisfying DO-NOT #5.
      const { commands } = await launchMut.mutateAsync({
        taskId: task.taskId,
        resume: true,
      });
      const command = pickPlatformCommand(commands);
      await writeClipboard(command);
      flashCopied("Resume command copied");
    } catch (err) {
      setCtaError(err instanceof Error ? err.message : String(err));
    }
  }, [launchMut, task.taskId, flashCopied]);

  const handleClose = useCallback(() => {
    closeMut.mutate(task.taskId);
  }, [closeMut, task.taskId]);

  const handleDelete = useCallback(() => {
    // Terminal / draft / launch_failed / jsonl_missing → delete without
    // confirmation (there's no live CLI to worry about stranding).
    if (isTerminalState(task.state) || task.state === "draft" || task.state === "launch_failed" || task.state === "jsonl_missing") {
      deleteMut.mutate(task.taskId);
      return;
    }
    setConfirmDeleteOpen(true);
  }, [deleteMut, task.state, task.taskId]);

  return (
    <header
      className="relative flex w-full items-center gap-4 border-b border-[var(--color-border,#e0dbd4)] bg-[var(--color-surface,#ffffff)] px-6 py-3"
      data-testid="task-detail-header"
    >
      <Link
        to="/"
        className="text-[var(--color-muted,#6b7280)] transition hover:text-[var(--color-text,#1a1a1a)]"
        aria-label="Back to board"
        data-testid="task-detail-back"
      >
        <ArrowLeft size={16} />
      </Link>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <EditableTaskTitle task={task} />
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-semibold ${STATE_BADGE_STYLES[task.state]}`}
            data-testid="task-state-badge"
          >
            {task.state}
          </span>
          <ProjectChipMenu task={task} />
        </div>
      </div>

      <div className="flex items-center gap-2" data-testid="task-detail-actions">
        {cta === "launch" && (
          <button
            type="button"
            onClick={() => void handleLaunch()}
            disabled={launchMut.isPending}
            className="inline-flex items-center gap-2 rounded-[var(--radius-button,8px)] bg-[var(--color-primary,#6b5e56)] px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-[var(--color-primary-hover,#5a4f48)] disabled:opacity-60"
            data-testid="cta-launch-in-terminal"
            aria-label="Launch in Terminal"
          >
            <TerminalIcon size={14} />
            {launchMut.isPending
              ? "Preparing…"
              : copiedLabel === "Launch command copied"
              ? "Copied — paste into terminal"
              : "Launch in Terminal"}
          </button>
        )}
        {cta === "resume" && (
          <button
            type="button"
            onClick={() => void handleResume()}
            disabled={launchMut.isPending}
            className="inline-flex items-center gap-2 rounded-[var(--radius-button,8px)] bg-[var(--color-primary,#6b5e56)] px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-[var(--color-primary-hover,#5a4f48)] disabled:opacity-60"
            data-testid="cta-copy-resume-command"
            aria-label="Copy resume command"
          >
            {copiedLabel === "Resume command copied" ? (
              <Copy size={14} />
            ) : (
              <Rocket size={14} />
            )}
            {launchMut.isPending
              ? "Preparing…"
              : copiedLabel === "Resume command copied"
              ? "Copied — paste into terminal"
              : "Copy Resume Command"}
          </button>
        )}

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              aria-label="More actions"
              className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-button,8px)] border border-[var(--color-border,#e0dbd4)] bg-[var(--color-surface,#ffffff)] text-[var(--color-muted,#6b7280)] transition hover:bg-[var(--color-muted-bg,#ede8e1)] hover:text-[var(--color-text,#1a1a1a)]"
              data-testid="task-detail-menu-trigger"
            >
              <MoreVertical size={16} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={6}
              className="z-50 min-w-[180px] rounded-lg border border-[var(--color-border,#e0dbd4)] bg-[var(--color-surface,#ffffff)] p-1 shadow-[var(--shadow-card,0_6px_30px_rgba(0,0,0,0.10))]"
              data-testid="task-detail-menu"
            >
              <DropdownMenu.Item
                disabled={isTerminalState(task.state)}
                onSelect={() => handleClose()}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--color-text,#1a1a1a)] outline-none transition hover:bg-[var(--color-muted-bg,#ede8e1)] data-[disabled]:cursor-not-allowed data-[disabled]:opacity-60"
                data-testid="task-detail-menu-close"
              >
                <X size={14} className="text-[var(--color-muted,#6b7280)]" />
                Close task
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => handleDelete()}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--color-error,#DC2626)] outline-none transition hover:bg-[var(--color-error,#DC2626)]/10"
                data-testid="task-detail-menu-delete"
              >
                <Trash2 size={14} className="text-[var(--color-error,#DC2626)]" />
                Delete task
              </DropdownMenu.Item>
              <DropdownMenu.Separator className="my-1 h-px bg-[var(--color-border,#e0dbd4)]" />
              <DropdownMenu.Item
                onSelect={(e) => {
                  e.preventDefault();
                  setShowDebug((v) => !v);
                }}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--color-muted,#6b7280)] outline-none transition hover:bg-[var(--color-muted-bg,#ede8e1)]"
                data-testid="task-detail-menu-toggle-debug"
              >
                <ChevronUp
                  size={14}
                  style={{ transform: showDebug ? "none" : "rotate(180deg)" }}
                />
                {showDebug ? "Hide session details" : "Show session details"}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {ctaError && (
        <span
          role="alert"
          className="absolute right-6 top-full mt-1 rounded bg-[var(--color-error,#DC2626)]/10 px-2 py-0.5 text-[11px]"
          style={{ color: "var(--color-error, #DC2626)" }}
          data-testid="task-detail-cta-error"
        >
          {ctaError}
        </span>
      )}

      {showDebug && (
        <div
          className="absolute left-0 right-0 top-full z-40 border-b border-[var(--color-border,#e0dbd4)] bg-[var(--color-bg,#f5f0eb)] px-6 py-2"
          data-testid="task-detail-session-metadata"
        >
          <SessionMetadata task={task} />
        </div>
      )}

      <ConfirmDeleteDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        task={task}
        onConfirm={() => {
          setConfirmDeleteOpen(false);
          deleteMut.mutate(task.taskId);
        }}
      />
    </header>
  );
}
