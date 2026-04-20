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
 *   - View toggle (Board/List): out of scope for B1 — no existing list
 *     view, adding one requires new routing/state.
 *   - Global `i` shortcut retained.
 *
 * Preserved testids:
 *   task-board-page, column-draft, column-in-progress, column-done,
 *   create-menu-*, preview-button, task-card-<id>.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { CreateMenuSplitButton } from "../components/external/CreateMenuSplitButton";
import { PreviewButton } from "../components/external/PreviewButton";
import { ProjectFilterDropdown } from "../components/external/ProjectFilterDropdown";
import { NewIssueModal } from "../components/external/NewIssueModal";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";

export default function TaskBoardPage() {
  const queryClient = useQueryClient();
  const { data: tasks = [], isLoading } = useExternalTasks();
  const { data: projects = [] } = useProjects();
  const { activeProjectId } = useProjectFilter();

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
      {/* Header — project selector (IS the title) + right-side actions */}
      <header
        className="flex flex-wrap items-center gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-3"
        data-testid="task-board-header"
      >
        <ProjectFilterDropdown />

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

      {/* Board */}
      {isLoading ? (
        <div className="p-6 text-sm text-[var(--color-muted)]">Loading…</div>
      ) : (
        <div
          className="flex flex-1 items-start gap-4 overflow-x-auto overflow-y-hidden p-6"
          data-testid="task-board-columns"
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
 */
const COLUMN_STYLES: Record<ColumnTone, ColumnStyle> = {
  draft: {
    // Draft uses the muted-bg token (warm beige) + a soft-muted top
    // border. #9ca3af in the mockup is close to --color-muted; using the
    // token keeps central theming coherent with Phase A.
    bg: "var(--color-muted-bg)",
    border: "var(--color-muted)",
    header: "var(--color-muted)",
    count: { bg: "rgba(107,114,128,0.15)", fg: "var(--color-muted)" },
  },
  inprogress: {
    // Amber 8% tint + warning border + warning-text header (#b45309 in
    // mockup; we use the warning-text token = #92400E which is close
    // enough and already Phase-A-approved).
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
      className="flex max-h-full w-[300px] min-w-[300px] shrink-0 flex-col overflow-hidden rounded-[var(--radius-card)]"
      style={{ background: s.bg }}
      data-testid={testId}
    >
      {/* Colored 3px top border — rendered as a separate element so the
          column bg tint shows through without clipping the rounded corners. */}
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
