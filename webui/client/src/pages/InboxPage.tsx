/*
 * Inbox — "best-effort" pending interactions across tracked external-launch
 * tasks. Webui cannot answer the LLM (external-launch invariant — see
 * CLAUDE.md DO-NOT #3), so this surface only helps the user route an
 * answer to their own terminal via clipboard shortcuts.
 *
 * Iterate 3 remediation v2 / Surface 4 (2026-04-21) — redesign:
 *   - Removed `ProjectFilterDropdown` entirely. Cards are now grouped by
 *     project (collapsible `<details>`, default-open) with the existing
 *     session UUID sub-grouping preserved inside each project section.
 *   - Removed the per-card Answer POST `<Link>`, the Dismiss button, and
 *     the "best-effort" pill badge. Webui does not answer Claude; the
 *     external-launch invariant means every answer path is clipboard →
 *     user's terminal.
 *   - Every card now carries a Launch-in-Terminal + Copy-Resume-Command
 *     top row (same semantics as TaskCard), plus the existing option
 *     pills (now clipboard shortcuts for "Answer: <pill>") and freetext
 *     row (clipboard-copies the typed text).
 *   - Wrapped the body in `.page-container` (1280 max-width, 24 px padding)
 *     so the Inbox aligns with Projects / Settings.
 *
 * Load-bearing testids (existing Playwright specs rely on them):
 *   inbox-page, inbox-empty, inbox-session-<uuid>, inbox-item-<toolUseId>,
 *   inbox-freetext-input, inbox-freetext-send, inbox-option-<i>,
 *   inbox-task-context-pill-<toolUseId>, inbox-header-count,
 *   inbox-group-project-label-<sessionUuid>.
 *
 * New testids added in v2:
 *   inbox-project-group-<projectId>,
 *   inbox-project-group-toggle-<projectId>,
 *   inbox-launch-<toolUseId>, inbox-copy-resume-<toolUseId>.
 */

import { useMemo, useState } from "react";
import {
  Copy,
  Hammer,
  ListChecks,
  Palette,
  FlaskConical,
  Rocket,
  ShieldAlert,
  ShieldCheck,
  Send,
  Terminal as TerminalIcon,
  Workflow,
} from "lucide-react";

import { askUserQuestionSummary } from "../external/session-parser";
import { useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useLaunchTask } from "../hooks/useLaunchTask";
import { useProjects } from "../hooks/useProjects";
import { classifyPhase } from "../lib/classifyPhase";
import { formatRelativeTime } from "../lib/formatTime";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";
import type { CopyCommandForms, ExternalTask, InboxItem } from "../lib/externalApi";
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

  const sessionGroups = useMemo(() => groupBySession(items), [items]);

  // Bucket session groups by project. A session without a matching task (or
  // an "unassigned" task) falls into the "Unassigned" project.
  const projectGroups = useMemo<ProjectGroup[]>(() => {
    const map = new Map<string, ProjectGroup>();
    for (const sg of sessionGroups) {
      const task = tasksById.get(sg.taskId);
      const projectId =
        task && task.projectId !== UNASSIGNED_PROJECT_ID
          ? task.projectId
          : UNASSIGNED_PROJECT_ID;
      const projectName = resolveProjectName(task, projectsById);
      const existing = map.get(projectId);
      if (existing) {
        existing.sessions.push(sg);
        existing.totalItems += sg.items.length;
      } else {
        map.set(projectId, {
          projectId,
          projectName,
          sessions: [sg],
          totalItems: sg.items.length,
        });
      }
    }
    return Array.from(map.values());
  }, [sessionGroups, tasksById, projectsById]);

  const openCount = useMemo(
    () => projectGroups.reduce((sum, pg) => sum + pg.totalItems, 0),
    [projectGroups],
  );

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: "var(--color-bg)" }}
      data-testid="inbox-page"
    >
      {/* Header — 24px / 700 title + inline "(N open)" */}
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
      </header>

      {/* Body — wrapped in .page-container so Inbox aligns with Projects */}
      <div className="flex-1 overflow-y-auto" style={{ paddingBlock: "24px 40px" }}>
        <div className="page-container">
          {isLoading && (
            <div className="text-sm" style={{ color: "var(--color-muted)" }}>
              Loading…
            </div>
          )}

          {!isLoading && projectGroups.length === 0 && (
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

          <div className="flex flex-col" style={{ gap: "24px" }}>
            {projectGroups.map((pg) => (
              <ProjectSection key={pg.projectId} group={pg} tasksById={tasksById} />
            ))}
          </div>
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

interface ProjectGroup {
  projectId: string;
  projectName: string;
  sessions: SessionGroup[];
  totalItems: number;
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

/**
 * Collapsible project-group section — `<details open>` so the user sees
 * everything by default but can collapse noisy projects. The summary row
 * mirrors the header-style "UNASSIGNED · count" pattern used elsewhere in
 * the app but adds a chevron affordance for the expand/collapse state.
 */
function ProjectSection({
  group,
  tasksById,
}: {
  group: ProjectGroup;
  tasksById: Map<string, ExternalTask>;
}) {
  return (
    <details
      open
      data-testid={`inbox-project-group-${group.projectId}`}
      style={{
        background: "transparent",
        borderRadius: "var(--radius-card)",
      }}
    >
      <summary
        data-testid={`inbox-project-group-toggle-${group.projectId}`}
        className="flex cursor-pointer select-none items-center gap-2 outline-none"
        style={{
          listStyle: "none",
          padding: "6px 4px 10px",
          color: "var(--color-muted)",
        }}
      >
        <span
          aria-hidden="true"
          className="inline-block transition-transform"
          style={{
            fontSize: "10px",
            lineHeight: 1,
            color: "var(--color-muted)",
          }}
        >
          ▾
        </span>
        <span
          className="font-semibold uppercase"
          style={{
            fontSize: "12px",
            letterSpacing: "0.6px",
            color: "var(--color-text)",
          }}
        >
          {group.projectName}
        </span>
        <span
          style={{
            fontSize: "11px",
            color: "var(--color-muted)",
            fontWeight: 500,
          }}
        >
          ({group.totalItems} open)
        </span>
      </summary>

      <div className="flex flex-col" style={{ gap: "16px", paddingLeft: "4px" }}>
        {group.sessions.map((sg) => {
          const task = tasksById.get(sg.taskId);
          return (
            <section
              key={sg.sessionUuid}
              data-testid={`inbox-session-${sg.sessionUuid}`}
            >
              {/* Session sub-header — mono UUID chip */}
              <div
                className="mb-2 flex items-center gap-2"
                style={{ paddingLeft: "4px" }}
              >
                <span
                  className="font-mono"
                  style={{
                    fontSize: "10px",
                    color: "var(--color-muted)",
                    opacity: 0.7,
                  }}
                  data-testid={`inbox-group-project-label-${sg.sessionUuid}`}
                >
                  session {sg.sessionUuid.slice(0, 8)}
                </span>
              </div>

              <div className="flex flex-col" style={{ gap: "12px" }}>
                {sg.items.map((item) => (
                  <InboxRow key={item.toolUseId} item={item} task={task} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </details>
  );
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
 * InboxRow — single question card.
 *
 * Shape (v2 / surface 4):
 *   ┌──┬──────────────────────────────────────────────────┐
 *   │▐▌│ [pill] build · 02-dashboard            2h ago   │
 *   │▐▌│ question text …                                  │
 *   │▐▌│ [Launch] [Copy resume]                           │
 *   │▐▌│ [pill] JWT [pill] Session                        │
 *   │▐▌│ or [input your answer]  [Copy]                   │
 *   └──┴──────────────────────────────────────────────────┘
 *    ^3px amber left strip; card keeps --color-surface bg.
 */
function InboxRow({
  item,
  task,
}: {
  item: InboxItem;
  task: ExternalTask | undefined;
}) {
  const isAUQ = item.toolName === "AskUserQuestion";
  const summary = isAUQ ? askUserQuestionSummary(item.input) : null;

  // Best-effort phase derivation from the task title. classifyPhase returns
  // null if nothing matches — in that case we skip the pill entirely.
  const phase = useMemo<string | null>(() => {
    if (!task?.title) return null;
    return classifyPhase(task.title, KNOWN_PHASES as unknown as string[]);
  }, [task?.title]);

  const timeAgo = useMemo<string | null>(() => {
    const stamp = task?.launchedAt ?? task?.createdAt;
    return stamp ? formatRelativeTime(stamp) : null;
  }, [task?.launchedAt, task?.createdAt]);

  // Clipboard helpers. Every answer path is clipboard → user's terminal —
  // webui never POSTs an answer (external-launch invariant).
  const [freetext, setFreetext] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const writeClipboardLocal = async (text: string): Promise<void> => {
    try {
      if (
        typeof navigator !== "undefined" &&
        navigator.clipboard?.writeText
      ) {
        await navigator.clipboard.writeText(text);
        return;
      }
    } catch {
      /* fall through to the execCommand fallback */
    }
    // Hard fallback for non-secure contexts. Match the pattern used in
    // TerminalLaunchButton / TaskDetailHeader for consistency.
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
  };
  const flashFeedback = (msg: string) => {
    setFeedback(msg);
    setTimeout(() => setFeedback(null), 2200);
  };
  const handleOption = (opt: string) => {
    void writeClipboardLocal(`Answer: ${opt}`);
    flashFeedback(`Copied "Answer: ${opt}" — paste into terminal`);
  };
  const handleFreetextSend = () => {
    const trimmed = freetext.trim();
    if (!trimmed) return;
    void writeClipboardLocal(`Answer: ${trimmed}`);
    flashFeedback("Copied — paste into terminal");
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
      {/* Top row: context pill + time-ago. Answer POST + Dismiss buttons
          were removed in v2 — external-launch invariant. */}
      <div className="mb-[10px] flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {phase && PhaseIcon && task && (
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
          )}
        </div>
        {timeAgo && (
          <span
            className="shrink-0 text-[12px] font-normal"
            style={{ color: "var(--color-muted)" }}
          >
            {timeAgo}
          </span>
        )}
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

          {/* Primary CTA row — Launch + Copy Resume (mirrors TaskCard CTA
              pattern; VS Code slot omitted because the VS Code extension
              bridge isn't wired into webui yet — surfaces as soon as it
              lands.) */}
          {task && (
            <div
              className="flex flex-wrap items-center"
              style={{ gap: "8px", marginTop: "4px", marginBottom: "12px" }}
            >
              <InboxLaunchButton
                task={task}
                mode="launch"
                testId={`inbox-launch-${item.toolUseId}`}
              />
              <InboxLaunchButton
                task={task}
                mode="resume"
                testId={`inbox-copy-resume-${item.toolUseId}`}
              />
            </div>
          )}

          {/* Option pills (clipboard shortcuts for "Answer: <opt>") */}
          {summary.options.length > 0 && (
            <div
              className="flex flex-wrap items-center"
              style={{ gap: "8px", marginTop: "4px" }}
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

          {/* Freetext row: "or" divider + input + clipboard copy button */}
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
                Copy
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

/**
 * Inbox-specific launch button. We cannot reuse `<TerminalLaunchButton>`
 * directly because that component couples the CTA mode to `task.state`
 * (draft → launch, otherwise → resume). The Inbox shows pending tool_use
 * questions that by definition come from active sessions, so the primary
 * CTA is almost always "Copy resume command" — but we also render an
 * explicit "Launch" action so users restarting from a terminated state
 * still have a path. Internally this uses the same `useLaunchTask`
 * mutation + clipboard helper.
 */
function InboxLaunchButton({
  task,
  mode,
  testId,
}: {
  task: ExternalTask;
  mode: "launch" | "resume";
  testId: string;
}) {
  const launchMut = useLaunchTask();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    setError(null);
    try {
      const { commands } = await launchMut.mutateAsync({
        taskId: task.taskId,
        resume: mode === "resume",
      });
      const command = pickPlatformCommand(commands);
      await writeClipboardModule(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const Icon = mode === "launch" ? TerminalIcon : copied ? Copy : Rocket;
  const idleLabel = mode === "launch" ? "Launch in Terminal" : "Copy Resume Command";
  const busyLabel = "Preparing…";
  const doneLabel = "Copied — paste into terminal";
  const label = launchMut.isPending ? busyLabel : copied ? doneLabel : idleLabel;

  return (
    <>
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={launchMut.isPending}
        data-testid={testId}
        className="inline-flex items-center gap-2 rounded-[var(--radius-button)] font-semibold text-white shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60"
        style={{
          background: "var(--color-primary)",
          padding: "7px 14px",
          fontSize: "13px",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "var(--color-primary-hover)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "var(--color-primary)";
        }}
      >
        <Icon size={14} />
        {label}
      </button>
      {error && (
        <span
          role="alert"
          className="text-[11px]"
          style={{ color: "var(--color-error)" }}
        >
          {error}
        </span>
      )}
    </>
  );
}

function pickPlatformCommand(commands: CopyCommandForms): string {
  if (typeof navigator === "undefined") return commands.posix;
  return /windows/i.test(navigator.userAgent) ? commands.powershell : commands.posix;
}

async function writeClipboardModule(text: string): Promise<void> {
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
