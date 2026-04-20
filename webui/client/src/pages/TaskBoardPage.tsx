/*
 * Task Board — list view with a per-project filter chip bar + the
 * `+ New ▾` split-button + conditional Preview button.
 *
 * Iterate 3 section 03:
 *   - Replaces the section-02 inline create-task form with the
 *     CreateMenuSplitButton (primary fires actions[0], caret opens
 *     dropdown of all actions).
 *   - Mounts NewIssueModal as a singleton — local state tracks which
 *     action was clicked so the modal can render the correct mode.
 *   - PreviewButton appears when server-materialized
 *     actions.preview.enabled === true.
 *   - Global `i` keyboard shortcut opens the New Iterate modal
 *     pre-filled with the active project (FR-03.14). Handler ignores
 *     typing-in-input states; regression-guards against any `c` or
 *     `Shift+C` binding (explicit omission, no listener at all).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Circle, PlayCircle } from "lucide-react";
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
import { NewIssueModal } from "../components/external/NewIssueModal";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";
import type { Project } from "../types";

export default function TaskBoardPage() {
  const queryClient = useQueryClient();
  const { data: tasks = [], isLoading } = useExternalTasks();
  const { data: projects = [] } = useProjects();
  const { activeProjectId, setActiveProjectId } = useProjectFilter();

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
    <div className="flex h-full flex-col gap-4 p-4" data-testid="task-board-page">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Task Board</h1>
          <p className="text-sm text-neutral-500">
            External-launch architecture: webui observes the JSONL, Claude Code runs in your own terminal.
          </p>
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

      <ProjectFilterChipBar
        projects={projects}
        tasks={tasks}
        activeProjectId={activeProjectId}
        onChange={setActiveProjectId}
      />

      {isLoading ? (
        <div className="text-sm text-neutral-400">Loading…</div>
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-4 md:grid-cols-3" data-testid="task-board-columns">
          <Column title="Draft" icon={<Circle size={14} />} items={columns.draft} />
          <Column title="In progress" icon={<PlayCircle size={14} />} items={columns.inProgress} />
          <Column title="Done" icon={<CheckCircle2 size={14} />} items={columns.done} />
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

interface ProjectFilterChipBarProps {
  projects: Project[];
  tasks: ExternalTask[];
  activeProjectId: string | null;
  onChange: (id: string | null) => void;
}

function ProjectFilterChipBar({
  projects,
  tasks,
  activeProjectId,
  onChange,
}: ProjectFilterChipBarProps) {
  const countByProject = useMemo(() => {
    const m = new Map<string, number>();
    for (const t of tasks) m.set(t.projectId, (m.get(t.projectId) ?? 0) + 1);
    return m;
  }, [tasks]);

  if (projects.length === 0) return null;

  return (
    <div
      className="flex flex-wrap items-center gap-2"
      data-testid="project-filter-chip-bar"
    >
      <Chip
        active={activeProjectId === null}
        onClick={() => onChange(null)}
        label="All projects"
        count={tasks.length}
        testId="project-chip-all"
      />
      {projects.map((p) => (
        <Chip
          key={p.id}
          active={activeProjectId === p.id}
          onClick={() => onChange(p.id)}
          label={p.name}
          count={countByProject.get(p.id) ?? 0}
          color={p.synthesized ? undefined : p.settings?.color}
          synthesized={p.synthesized}
          testId={`project-chip-${p.id === UNASSIGNED_PROJECT_ID ? "unassigned" : p.id}`}
        />
      ))}
    </div>
  );
}

interface ChipProps {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  color?: string;
  synthesized?: boolean;
  testId?: string;
}

function Chip({ active, onClick, label, count, color, synthesized, testId }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      data-active={active ? "true" : undefined}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
          : "border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
      } ${synthesized ? "italic" : ""}`}
    >
      {!synthesized && (
        <span
          aria-hidden="true"
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: color ?? (active ? "#ffffff80" : "var(--color-muted, #9ca3af)") }}
        />
      )}
      {synthesized && (
        <span
          aria-hidden="true"
          className={`h-2 w-2 shrink-0 rounded-full border ${active ? "border-white/60" : "border-neutral-400"}`}
        />
      )}
      <span>{label}</span>
      <span
        className={`font-mono text-[10px] ${
          active ? "text-white/80" : "text-neutral-400"
        }`}
      >
        {count}
      </span>
    </button>
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

function Column({
  title,
  icon,
  items,
}: {
  title: string;
  icon: React.ReactNode;
  items: ExternalTask[];
}) {
  return (
    <div
      className="flex min-w-[220px] flex-col gap-2 rounded border border-neutral-200 bg-neutral-50 p-2"
      data-testid={`column-${title.toLowerCase().replace(" ", "-")}`}
    >
      <div className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-neutral-600">
        {icon} {title} <span className="text-neutral-400">({items.length})</span>
      </div>
      {items.length === 0 && <div className="py-1 text-xs text-neutral-400">none</div>}
      {items.map((t) => (
        <TaskCard key={t.taskId} task={t} />
      ))}
    </div>
  );
}
