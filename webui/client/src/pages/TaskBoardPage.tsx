/*
 * Task Board — list + create. Click a card → navigates to /tasks/:taskId
 * for the LaunchRow + TranscriptViewer detail view.
 *
 * Replaces the old KanbanPage for the external-launch architecture.
 * Groups tasks into three columns: Draft, In progress, Done.
 *
 * Iterate 3 section 02:
 *   - Project filter chip bar above the columns, driven by the shared
 *     useProjectFilter hook. Chips derive from /api/projects (the server
 *     already appends the synthesized Unassigned row when relevant via
 *     ADR-037).
 *   - Inline task-creation form ships projectId in the request body:
 *     activeProjectId === null → "unassigned", else → activeProjectId.
 *     Phase stays empty — section 03 replaces this form with a modal that
 *     owns the phase dropdown.
 */

import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, CheckCircle2, Circle, PlayCircle } from "lucide-react";

import type { ExternalTask } from "../lib/externalApi";
import { useCreateExternalTask, useExternalTasks } from "../hooks/useExternalTasks";
import { useProjects } from "../hooks/useProjects";
import { useProjectFilter } from "../hooks/useProjectFilter";
import { TaskCard } from "../components/external/TaskCard";
import { UNASSIGNED_PROJECT_ID } from "../lib/projectIds";
import type { Project } from "../types";

export default function TaskBoardPage() {
  const navigate = useNavigate();
  const { data: tasks = [], isLoading } = useExternalTasks();
  const { data: projects = [] } = useProjects();
  const { activeProjectId, setActiveProjectId } = useProjectFilter();
  const createMut = useCreateExternalTask();
  const [title, setTitle] = useState("");
  const [cwd, setCwd] = useState("");

  // Client-side filter on projectId. The server-side endpoint currently
  // returns all tasks; filtering here keeps the network round-trip cheap
  // (tasks are already in the query cache) and lets the chip bar react
  // instantly to clicks. If task counts grow past ~500 the server should
  // start honouring ?projectId=<id> (noted for iterate 4+).
  const filteredTasks = useMemo<ExternalTask[]>(() => {
    if (activeProjectId === null) return tasks;
    return tasks.filter((t) => t.projectId === activeProjectId);
  }, [tasks, activeProjectId]);

  const columns = useMemo(() => groupByState(filteredTasks), [filteredTasks]);

  const handleCreate = useCallback(async () => {
    if (!title.trim() || !cwd.trim()) return;
    const task = await createMut.mutateAsync({
      title: title.trim(),
      cwd: cwd.trim(),
      pluginDirs: [],
      // Section 02 — the inline form adopts the current filter: explicit
      // project when one is active, UNASSIGNED otherwise. Phase stays
      // untouched (section 03 owns phase).
      projectId: activeProjectId ?? UNASSIGNED_PROJECT_ID,
    });
    setTitle("");
    navigate(`/tasks/${task.taskId}`);
  }, [title, cwd, createMut, navigate, activeProjectId]);

  return (
    <div className="flex h-full flex-col gap-4 p-4" data-testid="task-board-page">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Task Board</h1>
          <p className="text-sm text-neutral-500">
            External-launch architecture: webui observes the JSONL, Claude Code runs in your own terminal.
          </p>
        </div>
      </header>

      <ProjectFilterChipBar
        projects={projects}
        tasks={tasks}
        activeProjectId={activeProjectId}
        onChange={setActiveProjectId}
      />

      <section
        className="flex flex-wrap gap-2 rounded border border-neutral-200 bg-white p-3"
        data-testid="task-create-form"
      >
        <input
          type="text"
          className="min-w-[160px] flex-1 rounded border border-neutral-300 px-2 py-1 text-sm"
          placeholder="Task title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          data-testid="task-title-input"
        />
        <input
          type="text"
          className="min-w-[320px] flex-[2] rounded border border-neutral-300 px-2 py-1 font-mono text-sm"
          placeholder="Absolute working directory (e.g. C:\Users\me\my-project)"
          value={cwd}
          onChange={(e) => setCwd(e.target.value)}
          data-testid="task-cwd-input"
        />
        <button
          type="button"
          onClick={() => void handleCreate()}
          disabled={!title.trim() || !cwd.trim() || createMut.isPending}
          className="inline-flex items-center gap-1.5 rounded bg-neutral-800 px-3 py-1 text-sm text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="task-create-btn"
        >
          <Plus size={14} /> {createMut.isPending ? "Creating…" : "Create task"}
        </button>
      </section>

      {isLoading ? (
        <div className="text-sm text-neutral-400">Loading…</div>
      ) : (
        <div className="grid flex-1 grid-cols-1 gap-4 md:grid-cols-3" data-testid="task-board-columns">
          <Column title="Draft" icon={<Circle size={14} />} items={columns.draft} />
          <Column title="In progress" icon={<PlayCircle size={14} />} items={columns.inProgress} />
          <Column title="Done" icon={<CheckCircle2 size={14} />} items={columns.done} />
        </div>
      )}
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
