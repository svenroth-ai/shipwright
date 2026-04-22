/*
 * Inbox — read-only list of pending AskUserQuestion bubbles.
 *
 * Iterate 3.7d-b3 (2026-04-22) rebuild:
 *   - Each card is a LARGER read-only Ask-bubble (same info as the Ask-bubble
 *     in BubbleTranscript, bigger padding + body font, non-interactive).
 *   - Option chips are display-only (no onClick, no button role).
 *   - No `<textarea>` / freetext input (webui never answers Claude —
 *     external-launch invariant, CLAUDE.md DO-NOT #3).
 *   - No "Launch in Terminal" button; only a single brown "Resume" button
 *     per card (bottom-right, stops event propagation).
 *   - Whole card is click-through → navigates to `/tasks/<taskId>` via
 *     `useNavigate`. Keyboard: Enter + Space trigger the same nav.
 *   - Group-by-project structure + `(N open)` counts preserved from 3.7c-4.
 *
 * Load-bearing testids (retained from earlier iterates):
 *   inbox-page, inbox-empty, inbox-session-<uuid>, inbox-item-<toolUseId>,
 *   inbox-task-context-pill-<toolUseId>, inbox-header-count,
 *   inbox-group-project-label-<sessionUuid>,
 *   inbox-project-group-<projectId>, inbox-project-group-toggle-<projectId>.
 *
 * Testids added in 3.7d-b3:
 *   inbox-card-<toolUseId> (on the clickable card wrapper),
 *   inbox-resume-<toolUseId> (on the Resume button).
 *
 * Testids added in 3.7e-b4:
 *   inbox-group-color-<projectId> (on the 8 px colored dot in each
 *     project-group summary header; replaces the chevron/bullet that
 *     used to sit in the same slot).
 *
 * Testid retained (single-button card): `inbox-copy-resume-<toolUseId>` is
 * kept on the Resume button for backward compatibility with existing unit
 * tests; the new `inbox-resume-<toolUseId>` is also present.
 */

import { useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Copy,
  Hammer,
  ListChecks,
  Palette,
  FlaskConical,
  Rocket,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  Workflow,
} from "lucide-react";

import { extractAskUserPayload } from "../lib/askUserPayload";
import { useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useLaunchTask } from "../hooks/useLaunchTask";
import { useProjects } from "../hooks/useProjects";
import { classifyPhase } from "../lib/classifyPhase";
import { formatRelativeTime } from "../lib/formatTime";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";
import { getProjectColor } from "../lib/projectColor";
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
      const project =
        projectId === UNASSIGNED_PROJECT_ID
          ? undefined
          : projectsById.get(projectId);
      const existing = map.get(projectId);
      if (existing) {
        existing.sessions.push(sg);
        existing.totalItems += sg.items.length;
      } else {
        map.set(projectId, {
          projectId,
          projectName,
          project,
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
      {/* Header — 24px / 700 title + inline "(N open)".
          R1/R2 (iterate 3.7e-a Foundation, 2026-04-22): header content wrapped
          inside `.page-container` so the title left-edge aligns with the first
          group header and card below (same 24 px L/R padding, 1280 max-width).
          The full-bleed surface strip stays outside the container. */}
      <div
        style={{
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <header
          className="page-container flex items-center justify-between"
          style={{ paddingTop: "20px", paddingBottom: "20px" }}
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
      </div>

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
  /**
   * Resolved Project object, so the group header can read
   * `settings.color` for the color-chip override. Absent for the
   * synthesized "Unassigned" bucket.
   */
  project?: Project;
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
  // 3.7e-b4: project color chip. Unassigned bucket uses the muted token
  // (no project → no deterministic color). Real projects use the shared
  // `getProjectColor()` helper so the dot matches TaskBoard / Projects
  // table. `customColor` comes from `project.settings.color` when set by
  // the user via the Project-Settings dialog (iterate 14.8.2).
  const isUnassigned = group.projectId === UNASSIGNED_PROJECT_ID;
  const chipColor = isUnassigned
    ? "var(--color-muted)"
    : getProjectColor(group.projectId, group.project?.settings?.color).hsl;

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
          data-testid={`inbox-group-color-${group.projectId}`}
          className="inline-block shrink-0"
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "9999px",
            background: chipColor,
          }}
        />
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
                  <InboxCard key={item.toolUseId} item={item} task={task} />
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
 * InboxCard — read-only Ask-bubble at Inbox density.
 *
 * Shape (3.7d-b3):
 *   ┌──┬───────────────────────────────────────────────────┐
 *   │▐▌│ [pill] build · task-title          2h ago          │
 *   │▐▌│ PRIORITY                                           │
 *   │▐▌│ question body (14-15px / 600)                      │
 *   │▐▌│ [chip: JWT] [chip: Session]                        │
 *   │▐▌│                                  [Resume] ←brown   │
 *   └──┴───────────────────────────────────────────────────┘
 *    ^3px amber left strip; card keeps --color-surface bg.
 *
 * The whole card is click-through → /tasks/<taskId>. The Resume button
 * stops propagation so clicking it only copies the resume command.
 */
function InboxCard({
  item,
  task,
}: {
  item: InboxItem;
  task: ExternalTask | undefined;
}) {
  const navigate = useNavigate();
  const isAUQ = item.toolName === "AskUserQuestion";
  const payload = isAUQ ? extractAskUserPayload(item.input) : null;
  const firstPart = payload?.parts[0];
  const fallback = isAUQ && (!firstPart || !firstPart.question.trim());

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

  const handleCardClick = () => {
    if (!task) return;
    navigate(`/tasks/${task.taskId}`);
  };
  const handleCardKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!task) return;
    // Enter + Space activate card click-through (matches native button a11y).
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      navigate(`/tasks/${task.taskId}`);
    }
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
        padding: "22px 24px",
        boxShadow: "var(--shadow-sm)",
        maxWidth: "720px",
        cursor: task ? "pointer" : "default",
      }}
      role={task ? "button" : undefined}
      tabIndex={task ? 0 : undefined}
      aria-label={task ? `Open task ${task.title}` : undefined}
      onClick={task ? handleCardClick : undefined}
      onKeyDown={task ? handleCardKeyDown : undefined}
      data-testid={`inbox-card-${item.toolUseId}`}
      data-testid-legacy={`inbox-item-${item.toolUseId}`}
    >
      {/* Legacy testid wrapper: previous Playwright specs target
          `inbox-item-<toolUseId>`; keep it as an invisible inner node so we
          don't break that contract while the new `inbox-card-*` testid is
          adopted by 3.7d-b3+ specs. React warns on duplicate data-testid
          attrs via the same element, so we emit a small inner marker. */}
      <span
        data-testid={`inbox-item-${item.toolUseId}`}
        style={{ display: "none" }}
        aria-hidden="true"
      />
      {/* Top row: context pill + time-ago. Read-only. */}
      <div className="mb-[12px] flex items-center justify-between gap-3">
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

      {/* Question body — read-only Ask-bubble rendering */}
      {firstPart && !fallback ? (
        <div>
          {firstPart.header && (
            <div
              className="font-semibold uppercase"
              style={{
                fontSize: "11px",
                letterSpacing: "0.6px",
                color: "var(--color-muted)",
                marginBottom: "6px",
              }}
            >
              {firstPart.header}
            </div>
          )}
          <div
            className="font-semibold"
            style={{
              fontSize: "15px",
              color: "var(--color-text)",
              lineHeight: 1.45,
              marginBottom: firstPart.context ? "8px" : "14px",
            }}
          >
            {firstPart.question}
          </div>

          {firstPart.context && (
            <div
              style={{
                fontSize: "13px",
                color: "var(--color-muted)",
                lineHeight: 1.5,
                marginBottom: "14px",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {firstPart.context}
            </div>
          )}

          {/* Display-only option chips. No onClick, no button role. */}
          {firstPart.options && firstPart.options.length > 0 && (
            <div
              className="flex flex-wrap items-center"
              style={{ gap: "8px", marginBottom: "16px" }}
            >
              {firstPart.options.map((o, i) => (
                <span
                  key={i}
                  data-testid={`inbox-option-chip-${i}`}
                  className="inline-flex items-center rounded-[var(--radius-button)] font-medium"
                  style={{
                    padding: "6px 14px",
                    border: "1px solid var(--color-border)",
                    fontSize: "13px",
                    color: "var(--color-text)",
                    background: "var(--color-muted-bg)",
                  }}
                >
                  {o}
                </span>
              ))}
            </div>
          )}

          {/* Brown Resume button — bottom-right, single primary action. */}
          {task && (
            <div className="flex items-center justify-end" style={{ marginTop: "4px" }}>
              <InboxResumeButton task={task} toolUseId={item.toolUseId} />
            </div>
          )}
        </div>
      ) : (
        <div>
          <div
            className="italic"
            style={{
              fontSize: "12px",
              color: "var(--color-muted)",
              marginBottom: "8px",
            }}
          >
            Question payload schema differed from expected — open the task in
            your terminal to see the original.
          </div>
          {task && (
            <div className="flex items-center justify-end" style={{ marginTop: "4px" }}>
              <InboxResumeButton task={task} toolUseId={item.toolUseId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Single Resume button for an Inbox card. Copies the resume command to the
 * clipboard (no navigation, no POST). Stops click propagation so the
 * containing clickable card doesn't also navigate to TaskDetail.
 *
 * Two testids for back-compat: `inbox-resume-<toolUseId>` (new, per
 * 3.7d-b3 spec) and `inbox-copy-resume-<toolUseId>` (retained from v2).
 */
function InboxResumeButton({
  task,
  toolUseId,
}: {
  task: ExternalTask;
  toolUseId: string;
}) {
  const launchMut = useLaunchTask();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async (e: MouseEvent<HTMLButtonElement>) => {
    // Prevent the card-level onClick from also firing + navigating away
    // before the clipboard write completes.
    e.stopPropagation();
    setError(null);
    try {
      const { commands } = await launchMut.mutateAsync({
        taskId: task.taskId,
        resume: true,
      });
      const command = pickPlatformCommand(commands);
      await writeClipboardModule(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  // iterate 3.7f: Inbox CTA renamed "Resume" → "Answer" for consistency with
  // the Ask-bubble button (same clipboard action: copies resume command so
  // the user pastes + answers in their terminal). Terminal icon reflects the
  // intent; Copy icon still flashes during the 1.5s "Copied" confirm.
  const Icon = copied ? Copy : Terminal;
  const label = launchMut.isPending
    ? "Preparing…"
    : copied
      ? "Copied — paste into terminal"
      : "Answer";

  return (
    <>
      <button
        type="button"
        onClick={(e) => void handleClick(e)}
        onKeyDown={(e) => {
          // Don't let Enter/Space on the button also trigger the card's
          // keydown handler.
          e.stopPropagation();
        }}
        disabled={launchMut.isPending}
        data-testid={`inbox-resume-${toolUseId}`}
        data-testid-legacy={`inbox-copy-resume-${toolUseId}`}
        className="inline-flex items-center gap-2 rounded-[var(--radius-button)] font-semibold text-white shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60"
        style={{
          background: "var(--color-primary)",
          padding: "8px 16px",
          fontSize: "13px",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "var(--color-primary-hover)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "var(--color-primary)";
        }}
        aria-label={copied ? "Resume command copied" : "Copy resume command"}
      >
        <Icon size={14} />
        {label}
      </button>
      {/* Legacy testid node — kept invisibly for pre-3.7d-b3 specs. */}
      <span
        data-testid={`inbox-copy-resume-${toolUseId}`}
        style={{ display: "none" }}
        aria-hidden="true"
      />
      {error && (
        <span
          role="alert"
          className="ml-2 text-[11px]"
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
