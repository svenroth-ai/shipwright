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
 * Iterate 3.7e-b1 (2026-04-22):
 *   - Columns widened 320 → 360 px; gutter 32 → 40 px (plan S1.1).
 *   - New filter row above the columns inside .page-container — Status
 *     chips (multi-select; all selected = no filter). Phase filter is
 *     hidden entirely while ADR-045 is deferred (task.phase not populated).
 *
 * Preserved testids:
 *   task-board-page, task-board-header, task-board-columns,
 *   column-draft, column-in-progress, column-done,
 *   create-menu-*, preview-button, task-card-<id>.
 * New testids (iterate 3.7c-1):
 *   view-toggle-root, view-toggle-board, view-toggle-list,
 *   task-list-view, task-list-row-<id>.
 * Iterate 3.7d-b1: the kanban columns container also carries
 *   `data-page-container="true"` as a style hook (no new testid needed —
 *   the existing `task-board-columns` testid remains the board root).
 * Iterate 3.7e-b1:
 *   board-filter-status, board-filter-status-<value>.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import type {
  ActionDefinition,
  ExternalTask,
  ExternalTaskState,
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
  const { activeProjectId } = useProjectFilter();
  // iterate 3.7h (2026-04-22): use the GLOBAL (projectId-less) cache entry —
  // ProjectFilterDropdown also uses this so both consumers share it. Filter
  // happens client-side below via `projectFiltered`. The per-filter query-key
  // approach tried in 3.7f caused a cache-drift visual glitch when toggling
  // "All projects" from a single project (columns briefly empty while the
  // new key fetched). Single cache entry = zero drift.
  const { data: tasks = [], isLoading } = useExternalTasks();
  const { data: projects = [] } = useProjects();
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

  // iterate 3.7h: client-side project filter against the single global
  // task list. ProjectFilterDropdown uses the same underlying cache entry,
  // so switching filters is a pure React re-render with no fetch wait.
  const projectFiltered = useMemo<ExternalTask[]>(() => {
    if (activeProjectId === null) return tasks;
    return tasks.filter((t) => t.projectId === activeProjectId);
  }, [tasks, activeProjectId]);

  // Status filter — iterate 3.7e-b1 (plan S1.4). Multi-select chip set;
  // empty = "All" (no filter). Stored in local React state (no URL params).
  const [statusFilter, setStatusFilter] = useState<Set<ExternalTaskState>>(
    () => new Set(),
  );
  const toggleStatus = useCallback((s: ExternalTaskState) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  }, []);
  const clearStatusFilter = useCallback(() => {
    setStatusFilter(new Set());
  }, []);

  const filteredTasks = useMemo<ExternalTask[]>(() => {
    if (statusFilter.size === 0) return projectFiltered;
    return projectFiltered.filter((t) => statusFilter.has(t.state));
  }, [projectFiltered, statusFilter]);

  // Per-state counts — computed on the project-filtered set (not the
  // status-filtered one) so the counts stay stable as the user clicks
  // chips. Matches GitHub/Linear filter-bar affordance.
  const statusCounts = useMemo<Record<ExternalTaskState, number>>(() => {
    const seed: Record<ExternalTaskState, number> = {
      draft: 0,
      awaiting_external_start: 0,
      active: 0,
      idle: 0,
      done: 0,
      launch_failed: 0,
      jsonl_missing: 0,
    };
    for (const t of projectFiltered) {
      if (t.state in seed) seed[t.state] += 1;
    }
    return seed;
  }, [projectFiltered]);

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
      {/* Header — full-bleed surface strip matching ProjectsPage (iterate 3.7g,
          Sven UAT 2026-04-22). Inner .page-container has 20px top/bottom padding
          + flex justify-between so title cluster (dropdown + view toggle) sits at
          the left content edge and the `+ New task` button sits at the right
          content edge, same geometry as `Projects` header. */}
      {/* iterate 3.7j (Sven UAT 2026-04-22): merged header + filter row into
          ONE surface strip with a single bottom border so the separation to
          the beige columns body is unambiguous. Previously the two white
          strips + double borders + small padding felt "zusammengewürgt". */}
      <div
        style={{
          background: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <header
          className="page-container flex items-center justify-between"
          style={{ paddingTop: "20px", paddingBottom: "12px" }}
          data-testid="task-board-header"
        >
          <div className="flex items-center gap-3">
            <ProjectFilterDropdown />
            <div
              className="h-6 w-px bg-[var(--color-border)]"
              aria-hidden="true"
            />
            <ViewToggle value={view} onChange={setView} />
          </div>
          <div className="flex items-center gap-2">
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
          </div>
        </header>
        <div className="page-container flex flex-wrap items-center gap-2" style={{ paddingTop: "4px", paddingBottom: "16px" }}>
            <span
              className="min-w-[46px] text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--color-muted)]"
              data-testid="board-filter-status"
            >
              Status
            </span>
            {STATUS_FILTER_OPTIONS.map((opt) => (
              <StatusChip
                key={opt.value}
                label={opt.label}
                value={opt.value}
                count={statusCounts[opt.value]}
                active={statusFilter.has(opt.value)}
                onClick={toggleStatus}
                tone={opt.tone}
              />
            ))}
            {statusFilter.size > 0 && (
              <button
                type="button"
                onClick={clearStatusFilter}
                className="ml-1 rounded-[6px] px-2 py-[3px] text-[11px] text-[var(--color-muted)] transition-colors hover:bg-[rgba(220,38,38,0.06)] hover:text-[var(--color-error)]"
                title="Reset status filter"
                data-testid="board-filter-status-reset"
              >
                Reset
              </button>
            )}
          </div>
        </div>

      {/* Body — board (kanban) or list.
          R1 (iterate 3.7e-a Foundation): kanban body uses `.page-container`
          too — same 1600 max-width + 24 px L/R padding as the header above,
          so the header's first element and the first column share the same
          pixel offset from the sidebar. List view keeps its own internal
          layout (handled in TaskList).
          Iterate 3.7e-b1: gap-8 → gap-10 (32 → 40 px gutter). */}
      {isLoading ? (
        <div className="p-6 text-sm text-[var(--color-muted)]">Loading…</div>
      ) : view === "list" ? (
        // iterate 3.7h (Sven UAT): wrap TaskList in .page-container so the
        // table respects the same L/R gutters as the header + filter row.
        // `w-full` forces the container to stretch to parent width; without
        // it the page-container shrunk to the inner content width (was
        // 889px instead of the expected 1280) because TaskList's child
        // wrapper didn't force horizontal stretch.
        <div className="page-container w-full pt-10 pb-8">
          <TaskList tasks={filteredTasks} />
        </div>
      ) : (
        <div
          // iterate 3.7g (Sven UAT): `justify-between` distributes the 3
          // fixed-width columns across the container — first column sits at
          // the container's left edge, last at the right edge, middle
          // centered between them. At narrower viewports the implicit gap
          // shrinks; at wider viewports it grows so the columns stay
          // pinned to the content-container edges (matches header+filter
          // alignment). `min-w-0` on columns would let them shrink — we
          // keep them fixed (360 px) so cards stay legible. Fallback gap-6
          // (24 px) for viewports narrow enough that justify-between
          // collapses.
          className="page-container flex w-full flex-1 items-start justify-between gap-6 overflow-x-auto overflow-y-hidden pt-10 pb-8"
          data-testid="task-board-columns"
          data-page-container="true"
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
      className="flex max-h-full w-[360px] min-w-[360px] shrink-0 flex-col overflow-hidden rounded-[var(--radius-card)]"
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

// ---------------------------------------------------------------------------
// Status filter chips — iterate 3.7e-b1 (plan S1.4).
// ---------------------------------------------------------------------------

/** Muted / warning / error-tone accents on the Failed chips match the
 *  mockup filter row (lines 958–966 of kanban-with-projects.html). */
type ChipTone = "neutral" | "warning" | "success" | "error";

interface StatusFilterOption {
  value: ExternalTaskState;
  label: string;
  tone: ChipTone;
}

/** Order locked to the 7 valid ExternalTaskState values; labels lowercased
 *  to match our existing StatePill vocabulary. */
const STATUS_FILTER_OPTIONS: StatusFilterOption[] = [
  { value: "draft", label: "draft", tone: "neutral" },
  { value: "awaiting_external_start", label: "awaiting", tone: "warning" },
  { value: "active", label: "active", tone: "warning" },
  { value: "idle", label: "idle", tone: "neutral" },
  { value: "done", label: "done", tone: "success" },
  { value: "launch_failed", label: "launch-failed", tone: "error" },
  { value: "jsonl_missing", label: "jsonl-missing", tone: "error" },
];

interface StatusChipProps {
  label: string;
  value: ExternalTaskState;
  count: number;
  active: boolean;
  tone: ChipTone;
  onClick: (value: ExternalTaskState) => void;
}

/** Thin chip following `.chip` from the mockup (lines 401–427). Active +
 *  hover share the `--color-primary` accent; inactive uses a neutral
 *  token-only tint. `tone` colors the border + count slot for error /
 *  warning-flavored rows so Failed stands out. */
function StatusChip({
  label,
  value,
  count,
  active,
  tone,
  onClick,
}: StatusChipProps) {
  const toneStyle =
    tone === "error"
      ? { color: "var(--color-error)", borderColor: "rgba(220,38,38,0.25)" }
      : tone === "warning"
        ? { color: "var(--color-warning-text)", borderColor: "var(--color-border)" }
        : tone === "success"
          ? { color: "var(--color-success-text)", borderColor: "var(--color-border)" }
          : { color: "var(--color-muted)", borderColor: "var(--color-border)" };
  const activeStyle = active
    ? {
        background: "var(--color-primary)",
        color: "#fff",
        borderColor: "var(--color-primary)",
      }
    : {};
  return (
    <button
      type="button"
      onClick={() => onClick(value)}
      data-testid={`board-filter-status-${value}`}
      data-active={active || undefined}
      aria-pressed={active}
      className="inline-flex items-center gap-[5px] rounded-[12px] border bg-transparent px-[10px] py-[3px] text-[11.5px] font-medium transition-colors hover:bg-[var(--color-muted-bg)]"
      style={{ ...toneStyle, ...activeStyle }}
    >
      <span>{label}</span>
      <span
        className="font-mono text-[10px]"
        style={{ opacity: active ? 1 : 0.8 }}
      >
        {count}
      </span>
    </button>
  );
}
