/*
 * Task Board — kanban view with header dropdown + 3-column grid.
 *
 * Iterate 3 remediation Phase B1 (2026-04-20):
 *   - Header rebuild: h1/subtitle removed; <ProjectFilterDropdown> IS the
 *     title region per mockup `webui/designs/screens/kanban-with-projects.html`.
 *   - Right-side actions: PreviewButton + CreateMenuSplitButton (unchanged
 *     behavior; restyled per mockup).
 *   - 3 columns (Draft / In progress / Done) with per-column colored top
 *     border + tinted bg + uppercase 13px header + count pill. No state
 *     renames — visual change only.
 *   - Status + Phase chip rows: deferred to Phase C. See
 *     project-docs/ADRs/ADR-045-taskboard-status-phase-chips-deferred.md.
 *   - Global `i` shortcut retained.
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21):
 *   - Board/List view toggle in the header (default: board). View persists
 *     to localStorage ("webui.taskBoardView") + URL ?view=list.
 *   - Column board uses wider gaps (20px) + wider horizontal padding
 *     (28px) so the 3-column layout breathes at 1280px. Per-column top
 *     stripes unchanged (3px), draft stripe color tightened to a
 *     perceptible shade against the warm-beige page bg.
 *
 * Iterate 3.7d-b1 (2026-04-22):
 *   - Board centered inside a 1600px max-width container so ultra-wide
 *     monitors get symmetric whitespace instead of a left-anchored board.
 *     Board still fills the width up to 1600px — no regression on 1280px.
 *   - Column gutter bumped 20 → 32px so the 3-column layout breathes.
 *   - List view rebuilt as a proper <table> (moved into TaskList.tsx).
 *
 * Preserved testids:
 *   task-board-page, task-board-header, task-board-columns,
 *   column-draft, column-in-progress, column-done,
 *   create-menu-*, preview-button, task-card-<id>.
 * New testids (iterate 3.7c-1):
 *   view-toggle-root, view-toggle-board, view-toggle-list,
 *   task-list-view, task-list-row-<id>.
 * Iterate 3.7d-b1: the kanban columns container also carries
 *   `data-board-container="true"` as a style hook (no new testid needed —
 *   the existing `task-board-columns` testid remains the board root).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import type {
  ActionDefinition,
  ExternalTask,
} from "../lib/externalApi";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useProjects } from "../hooks/useProjects";
import { useProjectFilter } from "../hooks/useProjectFilter";
import { useProjectActions } from "../hooks/useProjectActions";
import { TaskCard } from "../components/external/TaskCard";
import { TaskList } from "../components/external/TaskList";
import { ViewToggle, type TaskBoardView } from "../components/external/ViewToggle";
import { CreateMenuSplitButton } from "../components/external/CreateMenuSplitButton";
import { PreviewButton } from "../components/external/PreviewButton";
import { ProjectFilterDropdown } from "../components/external/ProjectFilterDropdown";
import { NewIssueModal } from "../components/external/NewIssueModal";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";

const VIEW_STORAGE_KEY = "webui.taskBoardView";
const VIEW_URL_PARAM = "view";

function readStoredView(): TaskBoardView {
  try {
    const v = localStorage.getItem(VIEW_STORAGE_KEY);
    return v === "list" ? "list" : "board";
  } catch {
    return "board";
  }
}

export default function TaskBoardPage() {
  const queryClient = useQueryClient();
  const { data: tasks = [], isLoading } = useExternalTasks();
  const { data: projects = [] } = useProjects();
  const { activeProjectId } = useProjectFilter();
  const [searchParams, setSearchParams] = useSearchParams();

  // View state — URL wins on mount, falls back to localStorage.
  const [view, setViewState] = useState<TaskBoardView>(() => {
    const urlView = searchParams.get(VIEW_URL_PARAM);
    if (urlView === "list" || urlView === "board") return urlView;
    return readStoredView();
  });

  const setView = useCallback(
    (next: TaskBoardView) => {
      setViewState(next);
      try {
        localStorage.setItem(VIEW_STORAGE_KEY, next);
      } catch {
        /* ignore */
      }
      setSearchParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          if (next === "board") {
            p.delete(VIEW_URL_PARAM);
          } else {
            p.set(VIEW_URL_PARAM, next);
          }
          return p;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  // Resolve the actions schema for the active project. When "All projects"
  // is selected, fall back to the first real project so the dropdown still
  // shows something — the modal itself re-picks the project at launch time.
  const resolvedProjectId = useMemo<string | null>(() => {
    if (activeProjectId && activeProjectId !== UNASSIGNED_PROJECT_ID) {
      return activeProjectId;
    }
    const first = projects.find((p) => !p.synthesized && p.id !== UNASSIGNED_PROJECT_ID);
    return first?.id ?? null;
  }, [activeProjectId, projects]);

  const actionsQuery = useProjectActions(resolvedProjectId);
  const actionsList: ActionDefinition[] = actionsQuery.data?.actions ?? [];

  const filteredTasks = useMemo<ExternalTask[]>(() => {
    if (activeProjectId === null) return tasks;
    return tasks.filter((t) => t.projectId === activeProjectId);
  }, [tasks, activeProjectId]);

  const columns = useMemo(() => groupByState(filteredTasks), [filteredTasks]);

  // NewIssueModal state — singleton per page.
  const [modalAction, setModalAction] = useState<ActionDefinition | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const openModal = useCallback((a: ActionDefinition) => {
    setModalAction(a);
    setModalOpen(true);
  }, []);

  // Global `i` shortcut — open the New Iterate modal (FR-03.14).
  useEffect(() => {
    const listener = (ev: KeyboardEvent) => {
      if (ev.key !== "i" && ev.key !== "I") return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      // Ignore while the user is typing in an input / textarea / contenteditable.
      const target = ev.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
        if (target.isContentEditable) return;
      }
      // Don't fire when the modal is already open (avoid re-opening on keystroke).
      if (modalOpen) return;

      const iterate = actionsList.find((a) => a.id === "new-iterate");
      if (iterate) {
        ev.preventDefault();
        openModal(iterate);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [actionsList, modalOpen, openModal]);

  return (
    <div
      className="flex h-full flex-col bg-[var(--color-bg)]"
      data-testid="task-board-page"
    >
      {/* Header — project selector (IS the title) + view toggle + right-side actions */}
      <header
        className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-3"
        data-testid="task-board-header"
      >
        <ProjectFilterDropdown />

        <div className="h-6 w-px bg-[var(--color-border)]" aria-hidden="true" />

        <ViewToggle value={view} onChange={setView} />

        <div className="flex-1" />

        <PreviewButton
          projectId={resolvedProjectId}
          enabled={Boolean(actionsQuery.data?.preview.enabled)}
          readyTimeoutSeconds={
            actionsQuery.data?.preview.ready_timeout_seconds ?? null
          }
        />
        <CreateMenuSplitButton
          actions={actionsList}
          onSelect={openModal}
          isLoading={actionsQuery.isLoading}
        />
      </header>

      {/* Body — board (kanban) or list.
          The kanban body is wrapped in a 1600px max-width container so
          ultra-wide monitors get symmetric whitespace on both sides while
          staying full-bleed at ≤1600px. `.page-container` is intentionally
          NOT reused (it caps at 1280px — too narrow for 3 × 320px
          columns + 2 × 32px gutters = 1024px bare minimum + gutters). */}
      {isLoading ? (
        <div className="p-6 text-sm text-[var(--color-muted)]">Loading…</div>
      ) : view === "list" ? (
        <TaskList tasks={filteredTasks} />
      ) : (
        <div
          className="mx-auto flex w-full max-w-[1600px] flex-1 items-start gap-8 overflow-x-auto overflow-y-hidden px-7 py-5"
          data-testid="task-board-columns"
          data-board-container="true"
        >
          <Column
            title="Backlog"
            testId="column-draft"
            items={columns.draft}
            tone="draft"
          />
          <Column
            title="In Progress"
            testId="column-in-progress"
            items={columns.inProgress}
            tone="inprogress"
          />
          <Column
            title="Done"
            testId="column-done"
            items={columns.done}
            tone="done"
          />
        </div>
      )}

      <NewIssueModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        action={modalAction}
        projectActions={actionsQuery.data}
        onTaskCreated={() => {
          // Invalidate the external-tasks list so the new Draft row
          // appears immediately instead of waiting up to 2s for the
          // next refetchInterval tick. Phase A3 — iterate 3 remediation.
          void queryClient.invalidateQueries({ queryKey: ["external-tasks"] });
        }}
      />
    </div>
  );
}

function groupByState(tasks: ExternalTask[]) {
  const draft: ExternalTask[] = [];
  const inProgress: ExternalTask[] = [];
  const done: ExternalTask[] = [];
  for (const t of tasks) {
    if (t.state === "draft") draft.push(t);
    else if (t.state === "done") done.push(t);
    else inProgress.push(t);
  }
  return { draft, inProgress, done };
}

type ColumnTone = "draft" | "inprogress" | "done";

interface ColumnStyle {
  bg: string;
  border: string;
  header: string;
  count: { bg: string; fg: string };
}

/**
 * Per-column palette per mockup lines 532–543. We keep the tones in JS so
 * the styles are colocated with the semantic names and Tailwind arbitrary
 * values stay compact.
 *
 * 3.7c-1: draft stripe bumped from the mockup's `#9ca3af` (which washes
 * out against our warm-beige bg) to `#6b7280` — still inside the mockup's
 * neutral palette, but perceptible side-by-side with In-Progress / Done.
 */
const COLUMN_STYLES: Record<ColumnTone, ColumnStyle> = {
  draft: {
    bg: "var(--color-muted-bg)",
    border: "var(--color-muted)",
    header: "var(--color-muted)",
    count: { bg: "rgba(107,114,128,0.18)", fg: "var(--color-muted)" },
  },
  inprogress: {
    // Amber 8% tint + warning border + warning-text header.
    bg: "rgba(217,119,6,0.08)",
    border: "var(--color-warning)",
    header: "var(--color-warning-text)",
    count: { bg: "var(--color-warning-bg)", fg: "var(--color-warning-text)" },
  },
  done: {
    // Blue 8% tint + info border + info-text header.
    bg: "rgba(59,130,246,0.08)",
    border: "var(--color-info)",
    header: "#2563eb",
    count: { bg: "var(--color-info-bg)", fg: "#2563eb" },
  },
};

interface ColumnProps {
  title: string;
  testId: string;
  items: ExternalTask[];
  tone: ColumnTone;
}

function Column({ title, testId, items, tone }: ColumnProps) {
  const s = COLUMN_STYLES[tone];
  return (
    <div
      className="flex max-h-full w-[320px] min-w-[320px] shrink-0 flex-col overflow-hidden rounded-[var(--radius-card)]"
      style={{ background: s.bg }}
      data-testid={testId}
    >
      {/* Colored 3px top border — rendered as a separate element so the
          column bg tint shows through without clipping the rounded corners.
          The per-tone `s.border` values are always 3px-perceptible; draft
          was tightened to --color-muted in 3.7c-1 to match the mockup's
          intent against our warm-beige page bg. */}
      <div
        aria-hidden="true"
        className="h-[3px] w-full"
        style={{ background: s.border }}
      />
      <div
        className="flex items-center gap-2 px-[14px] pb-[10px] pt-[14px] text-[13px] font-semibold uppercase tracking-[0.04em]"
        style={{ color: s.header }}
      >
        <span>{title}</span>
        <span
          className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-[10px] px-1.5 text-[11px] font-bold"
          style={{ background: s.count.bg, color: s.count.fg }}
        >
          {items.length}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto px-[10px] pb-[14px]">
        {items.length === 0 && (
          <div className="py-1 text-[11px] text-[var(--color-muted)]">none</div>
        )}
        {items.map((t) => (
          <TaskCard key={t.taskId} task={t} />
        ))}
      </div>
    </div>
  );
}
