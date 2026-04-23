/*
 * TaskDetailHeader — single header bar above the 3-pane body (iterate 3
 * section 04, FR-03.30; visual rebuild in iterate 3.7b-3 / Phase B3).
 *
 * Owns:
 *   - breadcrumb `Projects › <project.name>` above the title row
 *   - title + state badge (pulsing dot, color-coded to state) + project chip
 *   - sub-line: phase tag · Started {ago} · last event {ago} · {model}
 *   - state-dependent primary CTA (iterate 3.7e-b2, R3 button variants):
 *       draft / awaiting_external_start           → GREEN Launch
 *                                                   (var(--color-success))
 *       active / idle                             → BROWN Resume
 *                                                   (var(--color-primary))
 *       done / launch_failed / jsonl_missing      → no CTA
 *     Terminal icon is always left of the label on both buttons.
 *   - 3-dots menu: Rename · Copy session UUID · Close · Delete · debug toggle
 *
 * Regression guards:
 *   - NO chat composer anywhere (CLAUDE.md DO-NOT #3).
 *   - "Resume" COPIES TO CLIPBOARD — never spawns Claude
 *     (DO-NOT #5).
 *   - Fork has moved to iterate 4 — menu must NOT surface it.
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ChevronRight,
  ChevronUp,
  Clipboard,
  Folder,
  MoreVertical,
  Pencil,
  Terminal as TerminalIcon,
  Trash2,
  X,
} from "lucide-react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import type {
  CopyCommandForms,
  ExternalTask,
  ExternalTaskState,
} from "../../lib/externalApi";
import {
  useCloseExternalTask,
  useDeleteExternalTask,
} from "../../hooks/useExternalTasks";
import { useLaunchTask } from "../../hooks/useLaunchTask";
import { useProjects } from "../../hooks/useProjects";
import { useTaskTranscript } from "../../hooks/useTaskTranscript";
import { formatRelativeTime } from "../../lib/formatTime";
import {
  EditableTaskTitle,
  type EditableTaskTitleHandle,
} from "./EditableTaskTitle";
import { ProjectChipMenu } from "./ProjectChipMenu";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { SessionMetadata } from "./SessionMetadata";

/**
 * State-badge visual definition. Background + foreground use HSL-flavoured
 * tones that match the mockup chip palette; the `dot` is the pulsing
 * circle rendered as a ::before equivalent (inline <span> with a
 * Tailwind `animate-pulse`).
 */
const STATE_BADGE: Record<
  ExternalTaskState,
  { bg: string; fg: string; dot: string; label: string; pulse: boolean }
> = {
  draft: {
    bg: "bg-[var(--color-muted-bg,#ede8e1)]",
    fg: "text-[var(--color-muted,#6b7280)]",
    dot: "bg-[var(--color-muted,#6b7280)]",
    label: "Draft",
    pulse: false,
  },
  awaiting_external_start: {
    bg: "bg-[#FEF3C7]",
    fg: "text-[#92400E]",
    dot: "bg-[#D97706]",
    label: "Awaiting launch",
    pulse: true,
  },
  active: {
    bg: "bg-[#FEF3C7]",
    fg: "text-[#92400E]",
    dot: "bg-[#D97706]",
    label: "In progress",
    pulse: true,
  },
  idle: {
    bg: "bg-[var(--color-muted-bg,#ede8e1)]",
    fg: "text-[var(--color-muted,#6b7280)]",
    dot: "bg-[var(--color-muted,#6b7280)]",
    label: "Idle",
    pulse: false,
  },
  jsonl_missing: {
    bg: "bg-[#FEE2E2]",
    fg: "text-[#991B1B]",
    dot: "bg-[var(--color-error,#DC2626)]",
    label: "JSONL missing",
    pulse: false,
  },
  launch_failed: {
    bg: "bg-[#FEE2E2]",
    fg: "text-[#991B1B]",
    dot: "bg-[var(--color-error,#DC2626)]",
    label: "Launch failed",
    pulse: false,
  },
  done: {
    bg: "bg-[#D1FAE5]",
    fg: "text-[#065F46]",
    dot: "bg-[var(--color-success,#059669)]",
    label: "Done",
    pulse: false,
  },
};

type CtaMode = "launch" | "resume" | "terminal" | "none";

function ctaFor(state: ExternalTask["state"]): CtaMode {
  if (state === "draft") return "launch";
  // iterate 3.7f (Sven UAT 2026-04-22): awaiting_external_start means "Launch
  // command was copied to clipboard, user needs to paste it in a terminal".
  // The next logical action is to switch to that terminal — label "Terminal"
  // (same clipboard action as Resume; the copied command is the same).
  if (state === "awaiting_external_start" || state === "active") return "terminal";
  if (state === "idle") return "resume";
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
  const navigate = useNavigate();
  const deleteMut = useDeleteExternalTask();
  const projectsQ = useProjects();
  const transcript = useTaskTranscript(task.taskId);

  const [copiedLabel, setCopiedLabel] = useState<string | null>(null);
  const [ctaError, setCtaError] = useState<string | null>(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [uuidCopied, setUuidCopied] = useState(false);
  // 3.7d-b2 — controls the ProjectChipMenu popover rendered off the
  // "Move to project…" menu item. Opens the popover on the chip's legacy
  // position (near the title) but without rendering the chip itself.
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const copyResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const uuidResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const titleRef = useRef<EditableTaskTitleHandle | null>(null);

  const cta = ctaFor(task.state);
  const badge = STATE_BADGE[task.state];

  const projectName = useMemo(() => {
    const list = projectsQ.data ?? [];
    const found = list.find((p) => p.id === task.projectId);
    if (found) return found.name;
    if (task.projectId === "unassigned") return "Unassigned";
    return task.projectId;
  }, [projectsQ.data, task.projectId]);

  /**
   * Phase source priority (2026-04-23):
   *   1. `task.phaseLabel` (server-persisted via /launch when NewIssueModal
   *      passed the full action context). This is the authoritative user
   *      choice — preferred so a compliance task titled "audit drift"
   *      shows a Compliance badge, not whatever the title regex guesses.
   *   2. Fallback — best-effort regex on title (legacy tasks launched
   *      before the wiring, or externally-created tasks without a
   *      pre-captured phase).
   *
   * Styling map is keyed by phase id (lowercase) so the server-sent
   * `task.phase` + `task.phaseLabel` pair can look up its colors; the
   * `label` in the rendered chip always uses `phaseLabel` verbatim.
   */
  const phase = useMemo(() => {
    const styles: Record<string, { cls: string; dot: string }> = {
      project: { cls: "bg-[var(--color-muted-bg,#ede8e1)] text-[var(--color-muted,#6b7280)]", dot: "bg-[#9ca3af]" },
      design: { cls: "bg-[#F3E8FF] text-[#6B21A8]", dot: "bg-[#A855F7]" },
      plan: { cls: "bg-[#DBEAFE] text-[#1E40AF]", dot: "bg-[#3B82F6]" },
      build: { cls: "bg-[#FEF3C7] text-[#92400E]", dot: "bg-[#F59E0B]" },
      test: { cls: "bg-[#D1FAE5] text-[#065F46]", dot: "bg-[#059669]" },
      deploy: { cls: "bg-[#CCFBF1] text-[#115E59]", dot: "bg-[#14B8A6]" },
      changelog: { cls: "bg-[#E0E7FF] text-[#3730A3]", dot: "bg-[#6366F1]" },
      compliance: { cls: "bg-[#E0F2FE] text-[#075985]", dot: "bg-[#0EA5E9]" },
      security: { cls: "bg-[#FEE2E2] text-[#991B1B]", dot: "bg-[#DC2626]" },
      adopt: { cls: "bg-[#E2E8F0] text-[#334155]", dot: "bg-[#64748B]" },
      iterate: { cls: "bg-[var(--color-muted-bg,#ede8e1)] text-[var(--color-muted,#6b7280)]", dot: "bg-[var(--color-accent,#857568)]" },
    };

    if (task.phaseLabel && task.phase) {
      const style = styles[task.phase.toLowerCase()] ?? styles.build;
      return { label: task.phaseLabel, cls: style.cls, dot: style.dot };
    }

    const title = (task.title ?? "").toLowerCase();
    if (/plan/.test(title)) return { label: "Plan", ...styles.plan };
    if (/build|implement|fix/.test(title)) return { label: "Build", ...styles.build };
    if (/design|ui|mockup/.test(title)) return { label: "Design", ...styles.design };
    if (/test|qa|e2e/.test(title)) return { label: "Test", ...styles.test };
    if (/iterate/.test(title)) return { label: "Iterate", ...styles.iterate };
    return null;
  }, [task.phase, task.phaseLabel, task.title]);

  // Compute "last event" from transcript ticks (polling). When transcript is
  // still loading we fall back to launchedAt / createdAt.
  const startedAt = task.launchedAt ?? task.firstJsonlObservedAt ?? task.createdAt;
  const lastEventAt = task.lastJsonlSeenMtimeMs
    ? new Date(task.lastJsonlSeenMtimeMs).toISOString()
    : undefined;

  // Best-effort model name — the parser strips the raw JSONL, so we scan
  // the transcript text directly for the most recent `"model":"..."`
  // occurrence (assistant events emit it at the message level). Harmless
  // fallback to null when the transcript hasn't loaded yet.
  const modelName = useMemo<string | null>(() => {
    if (!transcript.content) return null;
    const re = /"model"\s*:\s*"([^"]+)"/g;
    let last: string | null = null;
    let m: RegExpExecArray | null;
    while ((m = re.exec(transcript.content)) !== null) {
      last = m[1];
    }
    return last;
  }, [transcript.content]);

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
    if (
      isTerminalState(task.state) ||
      task.state === "draft" ||
      task.state === "launch_failed" ||
      task.state === "jsonl_missing"
    ) {
      deleteMut.mutate(task.taskId, {
        onSuccess: () => navigate("/"),
      });
      return;
    }
    setConfirmDeleteOpen(true);
  }, [deleteMut, navigate, task.state, task.taskId]);

  const handleRename = useCallback(() => {
    titleRef.current?.startEdit();
  }, []);

  const handleCopyUuid = useCallback(async () => {
    try {
      await writeClipboard(task.sessionUuid);
      setUuidCopied(true);
      if (uuidResetTimer.current) clearTimeout(uuidResetTimer.current);
      uuidResetTimer.current = setTimeout(() => setUuidCopied(false), 1500);
    } catch {
      /* clipboard denied — no fatal path */
    }
  }, [task.sessionUuid]);

  return (
    <header
      className="relative flex w-full items-center gap-4 border-b border-[var(--color-border,#e0dbd4)] bg-[var(--color-surface,#ffffff)] px-6 py-3"
      data-testid="task-detail-header"
    >
      {/* Inline keyframes so we do not have to touch index.css. */}
      <style>{`@keyframes taskDetailPulseDot { 0%,100% { opacity: 1 } 50% { opacity: 0.4 } }`}</style>
      <Link
        to="/"
        className="text-[var(--color-muted,#6b7280)] transition hover:text-[var(--color-text,#1a1a1a)]"
        aria-label="Back to board"
        data-testid="task-detail-back"
      >
        <ArrowLeft size={16} />
      </Link>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <nav
          className="inline-flex items-center gap-1.5 text-[11px] text-[var(--color-muted,#6b7280)]"
          aria-label="Breadcrumb"
          data-testid="task-detail-breadcrumb"
        >
          <Link
            to="/projects"
            className="transition hover:text-[var(--color-text,#1a1a1a)]"
          >
            Projects
          </Link>
          <ChevronRight
            size={10}
            aria-hidden="true"
            className="opacity-50"
          />
          <span className="truncate">{projectName}</span>
        </nav>

        {/*
         * 3.7d-b2 — title + state badge must share a single flex row with
         * items-center (prior baseline alignment looked off because the
         * badge has extra padding). ProjectChipMenu is no longer rendered
         * here; the breadcrumb above already shows the project. Project
         * change happens via the "Move to project…" 3-dots menu item that
         * opens the controlled popover anchored below.
         */}
        <div
          className="relative flex flex-wrap items-center gap-2.5"
          data-testid="task-detail-title-row"
        >
          <EditableTaskTitle ref={titleRef} task={task} />
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${badge.bg} ${badge.fg}`}
            data-testid="task-state-badge"
          >
            <span
              className={`inline-block h-[7px] w-[7px] shrink-0 rounded-full ${badge.dot}`}
              data-testid="task-detail-state-dot"
              data-state={task.state}
              style={
                badge.pulse
                  ? {
                      animation: "taskDetailPulseDot 1.5s infinite",
                    }
                  : undefined
              }
            />
            {badge.label}
          </span>
          {/* Headless ProjectChipMenu: renders no visible chip, only the
           * popover when `projectPickerOpen` flips true. Popover anchors
           * relative to this title row. */}
          <ProjectChipMenu
            task={task}
            open={projectPickerOpen}
            onOpenChange={setProjectPickerOpen}
          />
        </div>

        <div
          className="flex flex-wrap items-center gap-2.5 font-mono text-[11px] text-[var(--color-muted,#6b7280)]"
          data-testid="task-detail-subline"
        >
          {phase && (
            <span
              className={`inline-flex items-center gap-1.5 rounded-[10px] px-2 py-0.5 font-sans text-[10px] font-semibold uppercase tracking-[0.04em] ${phase.cls}`}
            >
              <span
                className={`inline-block h-[5px] w-[5px] rounded-full ${phase.dot}`}
              />
              {phase.label}
            </span>
          )}
          {phase && (
            <span
              aria-hidden="true"
              className="inline-block h-[10px] w-px bg-[var(--color-border,#e0dbd4)]"
            />
          )}
          <span>
            Started {formatRelativeTime(startedAt)}
            {lastEventAt
              ? ` · last event ${formatRelativeTime(lastEventAt)}`
              : ""}
          </span>
          {modelName && (
            <>
              <span
                aria-hidden="true"
                className="inline-block h-[10px] w-px bg-[var(--color-border,#e0dbd4)]"
              />
              <span className="font-mono text-[11px]">{modelName}</span>
            </>
          )}
        </div>
      </div>

      <div
        className="flex items-center gap-2"
        data-testid="task-detail-actions"
      >
        {/*
         * Iterate 3.7e-b2 — Header primary CTA state-mapping (R3):
         *   draft / awaiting_external_start → GREEN Launch (var(--color-success))
         *   active / idle                   → BROWN Resume (var(--color-primary))
         *   done / launch_failed / jsonl_missing → no button
         * Terminal icon is ALWAYS left of the label (Foundation R3 guarantee),
         * even in the transient "Copied" state — no Rocket/Copy swap anymore.
         * Testids `cta-launch-in-terminal` + `cta-copy-resume-command` stay
         * load-bearing (Playwright specs 30/36/36b/43/48/70-d/70-f + unit tests).
         */}
        {cta === "launch" && (
          <button
            type="button"
            onClick={() => void handleLaunch()}
            disabled={launchMut.isPending}
            className="inline-flex items-center gap-2 rounded-[var(--radius-button,8px)] px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition disabled:opacity-60"
            style={{ background: "var(--color-success, #059669)" }}
            onMouseEnter={(ev) => {
              ev.currentTarget.style.background = "#047857";
            }}
            onMouseLeave={(ev) => {
              ev.currentTarget.style.background = "var(--color-success, #059669)";
            }}
            data-testid="cta-launch-in-terminal"
            data-color="green"
            aria-label="Launch command — copy to clipboard"
          >
            <TerminalIcon size={14} />
            {launchMut.isPending
              ? "Preparing…"
              : copiedLabel === "Launch command copied"
              ? "Copied — paste into terminal"
              : "Launch"}
          </button>
        )}
        {cta === "resume" && (
          <button
            type="button"
            onClick={() => void handleResume()}
            disabled={launchMut.isPending}
            className="inline-flex items-center gap-2 rounded-[var(--radius-button,8px)] bg-[var(--color-resume,#C08862)] px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-[var(--color-resume-hover,#A67352)] disabled:opacity-60"
            data-testid="cta-copy-resume-command"
            data-color="orange"
            aria-label="Resume command — copy to clipboard"
          >
            <TerminalIcon size={14} />
            {launchMut.isPending
              ? "Preparing…"
              : copiedLabel === "Resume command copied"
              ? "Copied — paste into terminal"
              : "Resume"}
          </button>
        )}
        {cta === "terminal" && (
          <button
            type="button"
            onClick={() => void handleResume()}
            disabled={launchMut.isPending}
            className="inline-flex items-center gap-2 rounded-[var(--radius-button,8px)] bg-[var(--color-primary,#6b5e56)] px-4 py-1.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-[var(--color-primary-hover,#5a4f48)] disabled:opacity-60"
            data-testid="cta-terminal"
            data-color="brown"
            aria-label="Terminal — copy resume command to clipboard"
          >
            <TerminalIcon size={14} />
            {launchMut.isPending
              ? "Preparing…"
              : copiedLabel === "Resume command copied"
              ? "Copied — paste into terminal"
              : "Terminal"}
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
              className="z-50 min-w-[200px] rounded-lg border border-[var(--color-border,#e0dbd4)] bg-[var(--color-surface,#ffffff)] p-1 shadow-[var(--shadow-card,0_6px_30px_rgba(0,0,0,0.10))]"
              data-testid="task-detail-menu"
            >
              <DropdownMenu.Item
                onSelect={() => handleRename()}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--color-text,#1a1a1a)] outline-none transition hover:bg-[var(--color-muted-bg,#ede8e1)]"
                data-testid="task-detail-menu-rename"
              >
                <Pencil size={14} className="text-[var(--color-muted,#6b7280)]" />
                Rename
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={(e) => {
                  // keep menu open briefly so the "Copied!" pip is visible
                  e.preventDefault();
                  void handleCopyUuid();
                }}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--color-text,#1a1a1a)] outline-none transition hover:bg-[var(--color-muted-bg,#ede8e1)]"
                data-testid="task-detail-menu-copy-uuid"
              >
                <Clipboard
                  size={14}
                  className="text-[var(--color-muted,#6b7280)]"
                />
                {uuidCopied ? "Copied!" : "Copy session UUID"}
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => {
                  // Let the Radix DropdownMenu close naturally; wait for
                  // its focus-scope to release BEFORE opening the Popover.
                  // 80 ms empirically covers Radix's cleanup + the fresh
                  // tick in which we can safely focus the new portal.
                  window.setTimeout(() => setProjectPickerOpen(true), 80);
                }}
                className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] text-[var(--color-text,#1a1a1a)] outline-none transition hover:bg-[var(--color-muted-bg,#ede8e1)]"
                data-testid="task-detail-menu-move-project"
              >
                <Folder
                  size={14}
                  className="text-[var(--color-muted,#6b7280)]"
                />
                Move to project…
              </DropdownMenu.Item>
              <DropdownMenu.Separator className="my-1 h-px bg-[var(--color-border,#e0dbd4)]" />
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
                <Trash2
                  size={14}
                  className="text-[var(--color-error,#DC2626)]"
                />
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
          deleteMut.mutate(task.taskId, {
            onSuccess: () => navigate("/"),
          });
        }}
      />
    </header>
  );
}
