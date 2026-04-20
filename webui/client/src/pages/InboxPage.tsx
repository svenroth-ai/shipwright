/*
 * Inbox — "best-effort" pending interactions across tracked external-launch
 * tasks. Round-3 plan integration explicitly labels the list as best-effort
 * because heuristic tool_use-without-tool_result correlation can false-
 * positive (long-running commands) and false-negative (plugin-owned
 * non-standard tool shapes). Users answer in their own chat client; webui
 * only surfaces the question here + offers dismiss.
 *
 * Iterate 3 remediation Phase B4 (2026-04-20) — visual rebuild:
 *   - Header: 24px/700 title + inline muted "(N open)" + ghost "Mark all
 *     read" button right-aligned.
 *   - Filter: header dropdown (shared ProjectFilterDropdown from Phase A6)
 *     replaces the old chip bar. Grouping stays by session UUID (product
 *     decision #2), but each group header now carries the project name
 *     alongside the 8-char UUID, derived via
 *       tasksById.get(g.taskId)?.projectId → projects.find(p => p.id === pid)?.name
 *     with "Unassigned" fallback for the UNASSIGNED_PROJECT_ID sentinel.
 *   - Rows: task-context-pill (muted-bg rounded 12px with lucide phase
 *     icon + phase name + task title), right-aligned time-ago, primary
 *     `var(--color-primary)` warm-brown Answer CTA (not cool black).
 *   - Options: clickable pills (border + rounded-button, hover primary
 *     border). No answer-POST endpoint exists server-side yet, so the
 *     graceful-degradation path writes the option text to the clipboard
 *     and shows inline "Answer in your terminal" feedback. When the API
 *     lands, swap the clipboard call for a POST in one place.
 *   - Freetext row: "or" divider + `<input>` with send button revealed
 *     when the input has content. Same clipboard fallback path.
 *
 * Load-bearing testids (iterate-2 + iterate-3 Playwright specs depend):
 *   inbox-page, inbox-empty, inbox-session-<uuid>, inbox-item-<toolUseId>,
 *   dismiss-<toolUseId>, answer-<toolUseId>.
 *
 * New testids (Phase B4):
 *   inbox-header-count, inbox-mark-all-read,
 *   inbox-project-filter-dropdown (wraps the shared primitive),
 *   inbox-group-project-label-<sessionUuid>,
 *   inbox-task-context-pill-<toolUseId>,
 *   inbox-option-<optionIndex>,
 *   inbox-freetext-input, inbox-freetext-send.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Hammer,
  ListChecks,
  Palette,
  FlaskConical,
  Rocket,
  ShieldAlert,
  ShieldCheck,
  Send,
  Workflow,
} from "lucide-react";

import { ProjectFilterDropdown } from "../components/external/ProjectFilterDropdown";
import { askUserQuestionSummary } from "../external/session-parser";
import { useDismissInboxItem, useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useProjectFilter } from "../hooks/useProjectFilter";
import { useProjects } from "../hooks/useProjects";
import { classifyPhase } from "../lib/classifyPhase";
import { formatRelativeTime } from "../lib/formatTime";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";
import type { ExternalTask, InboxItem } from "../lib/externalApi";
import type { Project } from "../types";

// Known phase ids (mirrors PIPELINE_PHASES but we intentionally don't couple
// to Kanban phaseMapping, which uses a slightly different vocab). Used as the
// classifyPhase allowlist to derive a best-effort phase tag for the context
// pill from the task title.
const KNOWN_PHASES = [
  "project",
  "design",
  "plan",
  "build",
  "test",
  "security",
  "compliance",
  "changelog",
  "deploy",
] as const;

export default function InboxPage() {
  const { data: items = [], isLoading } = useExternalInbox();
  const { data: tasks = [] } = useExternalTasks();
  const { data: projects = [] } = useProjects();
  const { activeProjectId } = useProjectFilter();
  const dismissMut = useDismissInboxItem();

  const tasksById = useMemo(() => {
    const m = new Map<string, ExternalTask>();
    for (const t of tasks) m.set(t.taskId, t);
    return m;
  }, [tasks]);

  const projectsById = useMemo(() => {
    const m = new Map<string, Project>();
    for (const p of projects) m.set(p.id, p);
    return m;
  }, [projects]);

  const groups = useMemo(() => groupBySession(items), [items]);

  // Filter groups by the shared active-project selection. Matches
  // TaskBoard semantics: null = All Projects keeps every group, including
  // orphans; a specific projectId drops groups whose task is from a
  // different project OR whose task record is missing entirely.
  const visibleGroups = useMemo<SessionGroup[]>(() => {
    if (activeProjectId === null) return groups;
    return groups.filter((g) => {
      const task = tasksById.get(g.taskId);
      return task?.projectId === activeProjectId;
    });
  }, [groups, tasksById, activeProjectId]);

  const openCount = useMemo(
    () => visibleGroups.reduce((sum, g) => sum + g.items.length, 0),
    [visibleGroups],
  );

  // "Mark all read" stub: no batch-dismiss endpoint exists yet. When one
  // lands, swap this for the mutation. For now: dismiss visible items in
  // sequence. Disabled when there's nothing to dismiss.
  const [markingAll, setMarkingAll] = useState(false);
  const [markAllMsg, setMarkAllMsg] = useState<string | null>(null);
  const handleMarkAllRead = async () => {
    if (openCount === 0) {
      setMarkAllMsg("Nothing to do yet");
      setTimeout(() => setMarkAllMsg(null), 2000);
      return;
    }
    setMarkingAll(true);
    try {
      for (const g of visibleGroups) {
        for (const it of g.items) {
          await dismissMut.mutateAsync(it.toolUseId).catch(() => {
            /* best-effort: ignore single-item failures */
          });
        }
      }
    } finally {
      setMarkingAll(false);
    }
  };

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "var(--color-bg)" }}
      data-testid="inbox-page"
    >
      {/* Header — 24px / 700 title + inline "(N open)" + Mark all read */}
      <header
        className="flex items-center justify-between"
        style={{
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
          padding: "20px 32px",
        }}
      >
        <div className="flex items-baseline gap-[10px]">
          <h1
            className="font-bold"
            style={{
              fontSize: "24px",
              color: "var(--color-text)",
              letterSpacing: "-0.01em",
            }}
          >
            Inbox
          </h1>
          <span
            className="font-medium"
            style={{
              fontSize: "14px",
              color: "var(--color-muted)",
            }}
            data-testid="inbox-header-count"
          >
            ({openCount} open)
          </span>
        </div>
        <div className="flex items-center gap-3">
          {markAllMsg && (
            <span
              className="text-[12px] italic"
              style={{ color: "var(--color-muted)" }}
            >
              {markAllMsg}
            </span>
          )}
          <button
            type="button"
            onClick={handleMarkAllRead}
            disabled={markingAll}
            data-testid="inbox-mark-all-read"
            className="rounded-[var(--radius-button)] px-3 py-[6px] text-[13px] font-medium transition-colors hover:bg-[var(--color-muted-bg)] disabled:opacity-50"
            style={{ color: "var(--color-primary)" }}
          >
            {markingAll ? "Marking…" : "Mark all read"}
          </button>
        </div>
      </header>

      {/* Filter row — shared dropdown, left-aligned */}
      <div
        className="flex items-center"
        style={{
          padding: "16px 32px 0",
        }}
        data-testid="inbox-project-filter-dropdown"
      >
        <ProjectFilterDropdown />
      </div>

      {/* Body */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ padding: "24px 32px 40px" }}
      >
        {isLoading && (
          <div className="text-sm" style={{ color: "var(--color-muted)" }}>
            Loading…
          </div>
        )}

        {!isLoading && visibleGroups.length === 0 && (
          <div
            className="p-4 text-sm"
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-button)",
              color: "var(--color-muted)",
            }}
            data-testid="inbox-empty"
          >
            No pending interactions.
          </div>
        )}

        <div className="flex flex-col" style={{ gap: "28px" }}>
          {visibleGroups.map((g) => {
            const task = tasksById.get(g.taskId);
            const projectName = resolveProjectName(task, projectsById);
            return (
              <section
                key={g.sessionUuid}
                data-testid={`inbox-session-${g.sessionUuid}`}
              >
                {/* Group header — project name + first-8 UUID (mono) */}
                <div
                  className="mb-3 flex items-center gap-2"
                  style={{ paddingLeft: "4px" }}
                >
                  <span
                    className="text-[12px] font-semibold uppercase"
                    style={{
                      color: "var(--color-muted)",
                      letterSpacing: "0.6px",
                    }}
                    data-testid={`inbox-group-project-label-${g.sessionUuid}`}
                  >
                    {projectName}
                  </span>
                  <span
                    className="font-mono text-[10px]"
                    style={{ color: "var(--color-muted)", opacity: 0.7 }}
                  >
                    {g.sessionUuid.slice(0, 8)}
                  </span>
                </div>

                <div className="flex flex-col" style={{ gap: "12px" }}>
                  {g.items.map((item) => (
                    <InboxRow
                      key={item.toolUseId}
                      item={item}
                      task={task}
                      onDismiss={() => dismissMut.mutate(item.toolUseId)}
                      dismissing={dismissMut.isPending}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface SessionGroup {
  sessionUuid: string;
  taskId: string;
  taskTitle: string;
  items: InboxItem[];
}

function groupBySession(items: InboxItem[]): SessionGroup[] {
  const groups = new Map<string, SessionGroup>();
  for (const item of items) {
    const existing = groups.get(item.sessionUuid);
    if (existing) {
      existing.items.push(item);
    } else {
      groups.set(item.sessionUuid, {
        sessionUuid: item.sessionUuid,
        taskId: item.taskId,
        taskTitle: item.taskTitle,
        items: [item],
      });
    }
  }
  return Array.from(groups.values());
}

function resolveProjectName(
  task: ExternalTask | undefined,
  projectsById: Map<string, Project>,
): string {
  if (!task) return "Unassigned";
  if (task.projectId === UNASSIGNED_PROJECT_ID) return "Unassigned";
  return projectsById.get(task.projectId)?.name ?? "Unassigned";
}

const PHASE_ICON: Record<
  string,
  React.ComponentType<{ size?: number; className?: string }>
> = {
  build: Hammer,
  design: Palette,
  plan: ListChecks,
  project: ListChecks,
  test: FlaskConical,
  deploy: Rocket,
  compliance: ShieldCheck,
  security: ShieldAlert,
  changelog: Workflow,
};

/**
 * InboxRow — mockup-accurate question card.
 *
 *   ┌──┬────────────────────────────────────────────────┬────────┐
 *   │▐▌│ [pill] build · 02-dashboard          2h ago   │[Answer]│
 *   │▐▌│ question text …                                │[×]     │
 *   │▐▌│ [pill] option A  [pill] option B               │        │
 *   │▐▌│ ── or ── [input type your answer…]  [send →]   │        │
 *   └──┴────────────────────────────────────────────────┴────────┘
 *    ^3px amber left strip (border-left). NOT a full amber bg.
 */
function InboxRow({
  item,
  task,
  onDismiss,
  dismissing,
}: {
  item: InboxItem;
  task: ExternalTask | undefined;
  onDismiss: () => void;
  dismissing: boolean;
}) {
  const isAUQ = item.toolName === "AskUserQuestion";
  const summary = isAUQ ? askUserQuestionSummary(item.input) : null;

  // Best-effort phase derivation from the task title. classifyPhase returns
  // null if nothing matches — in that case we skip the pill entirely per
  // spec.
  const phase = useMemo<string | null>(() => {
    if (!task?.title) return null;
    return classifyPhase(task.title, KNOWN_PHASES as unknown as string[]);
  }, [task?.title]);

  const timeAgo = useMemo<string | null>(() => {
    const stamp = task?.launchedAt ?? task?.createdAt;
    return stamp ? formatRelativeTime(stamp) : null;
  }, [task?.launchedAt, task?.createdAt]);

  // Graceful degradation: no answer-POST API exists. Copy the option to the
  // clipboard and surface inline feedback so the user knows to paste in
  // their terminal.
  const [freetext, setFreetext] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const ackCopy = (text: string) => {
    // navigator.clipboard may be missing in non-secure contexts; fall
    // through silently — the feedback still explains the intent.
    try {
      if (navigator?.clipboard?.writeText) {
        void navigator.clipboard.writeText(text);
      }
    } catch {
      /* noop */
    }
    setFeedback("Copied — answer in your terminal");
    setTimeout(() => setFeedback(null), 2200);
  };
  const handleOption = (opt: string) => ackCopy(opt);
  const handleFreetextSend = () => {
    const trimmed = freetext.trim();
    if (!trimmed) return;
    ackCopy(trimmed);
    setFreetext("");
  };

  const PhaseIcon = phase ? PHASE_ICON[phase] : null;

  return (
    <div
      className="transition-opacity"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderLeft: "3px solid var(--color-warning)",
        borderRadius: "var(--radius-button)",
        padding: "18px 20px",
        boxShadow: "var(--shadow-sm)",
        maxWidth: "680px",
      }}
      data-testid={`inbox-item-${item.toolUseId}`}
    >
      {/* Top row: context pill + time-ago + right-side actions */}
      <div className="mb-[10px] flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {phase && PhaseIcon && task ? (
            <span
              className="inline-flex items-center gap-[5px] rounded-[12px] font-semibold uppercase"
              style={{
                background: "var(--color-muted-bg)",
                color: "var(--color-muted)",
                fontSize: "11px",
                padding: "3px 10px",
                letterSpacing: "0.02em",
              }}
              data-testid={`inbox-task-context-pill-${item.toolUseId}`}
            >
              <PhaseIcon size={12} />
              <span className="truncate">
                {phase} / {task.title}
              </span>
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-[5px] rounded-[12px] font-semibold uppercase"
              style={{
                background: "var(--color-muted-bg)",
                color: "var(--color-muted)",
                fontSize: "11px",
                padding: "3px 10px",
                letterSpacing: "0.02em",
              }}
            >
              <AlertTriangle size={12} />
              best-effort
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {timeAgo && (
            <span
              className="text-[12px] font-normal"
              style={{ color: "var(--color-muted)" }}
            >
              {timeAgo}
            </span>
          )}
          <button
            type="button"
            onClick={onDismiss}
            disabled={dismissing}
            className="rounded-[var(--radius-button)] px-3 py-1 text-[12px] font-medium transition-colors hover:bg-[var(--color-muted-bg)] disabled:opacity-50"
            style={{
              border: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
            }}
            data-testid={`dismiss-${item.toolUseId}`}
          >
            Dismiss
          </button>
          <Link
            to={`/tasks/${item.taskId}`}
            className="inline-flex items-center rounded-[var(--radius-button)] px-3 py-1 text-[12px] font-medium text-white transition-colors hover:bg-[var(--color-primary-hover)]"
            style={{ background: "var(--color-primary)" }}
            data-testid={`answer-${item.toolUseId}`}
          >
            Answer
          </Link>
        </div>
      </div>

      {/* Question body */}
      {summary ? (
        <div>
          <div
            className="font-semibold"
            style={{
              fontSize: "14px",
              color: "var(--color-text)",
              lineHeight: 1.4,
              marginBottom: "6px",
            }}
          >
            {summary.question}
          </div>

          {summary.fallback && (
            <div
              className="italic"
              style={{
                fontSize: "10px",
                color: "var(--color-muted)",
                marginTop: "2px",
                marginBottom: "8px",
              }}
            >
              Question payload schema differed from expected.
            </div>
          )}

          {/* Option pills */}
          {summary.options.length > 0 && (
            <div
              className="flex flex-wrap items-center"
              style={{ gap: "8px", marginTop: "14px" }}
            >
              {summary.options.map((o, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleOption(o)}
                  data-testid={`inbox-option-${i}`}
                  className="rounded-[var(--radius-button)] font-medium transition-colors hover:bg-[var(--color-muted-bg)]"
                  style={{
                    padding: "7px 16px",
                    border: "1px solid var(--color-border)",
                    fontSize: "13px",
                    color: "var(--color-text)",
                    background: "var(--color-surface)",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "var(--color-primary)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--color-border)";
                  }}
                >
                  {o}
                </button>
              ))}
            </div>
          )}

          {/* Freetext row: "or" divider + input + send */}
          <div
            className="flex items-center"
            style={{ gap: "8px", marginTop: "10px" }}
          >
            <span
              className="font-normal"
              style={{
                fontSize: "12px",
                color: "var(--color-muted)",
                padding: "0 2px",
              }}
            >
              or
            </span>
            <input
              type="text"
              value={freetext}
              onChange={(e) => setFreetext(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleFreetextSend();
                }
              }}
              placeholder="Type your answer…"
              data-testid="inbox-freetext-input"
              className="rounded-[var(--radius-button)] outline-none transition-colors"
              style={{
                flex: 1,
                maxWidth: "360px",
                padding: "7px 12px",
                border: "1px solid var(--color-border)",
                fontSize: "13px",
                color: "var(--color-text)",
                background: "var(--color-bg)",
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = "var(--color-primary)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = "var(--color-border)";
              }}
            />
            {freetext.trim().length > 0 && (
              <button
                type="button"
                onClick={handleFreetextSend}
                data-testid="inbox-freetext-send"
                className="inline-flex items-center gap-1 rounded-[var(--radius-button)] font-medium text-white transition-colors hover:bg-[var(--color-primary-hover)]"
                style={{
                  padding: "7px 14px",
                  fontSize: "13px",
                  background: "var(--color-primary)",
                }}
              >
                <Send size={14} />
                Send
              </button>
            )}
          </div>

          {feedback && (
            <div
              className="italic"
              style={{
                fontSize: "11px",
                color: "var(--color-muted)",
                marginTop: "8px",
              }}
            >
              {feedback}
            </div>
          )}
        </div>
      ) : (
        <pre
          className="overflow-auto rounded p-1"
          style={{
            background: "var(--color-muted-bg)",
            fontSize: "10px",
            maxHeight: "8rem",
            color: "var(--color-text)",
          }}
        >
          {JSON.stringify(item.input, null, 2)}
        </pre>
      )}
    </div>
  );
}
