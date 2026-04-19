/*
 * Task Board — list + create. Click a card → navigates to /tasks/:taskId
 * for the LaunchRow + TranscriptViewer detail view.
 *
 * Replaces the old KanbanPage for the external-launch architecture.
 * Groups tasks into three columns: Draft, In progress, Done.
 */

import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, CheckCircle2, Circle, PlayCircle, AlertTriangle } from "lucide-react";

import type { ExternalTask } from "../lib/externalApi";
import {
  useCreateExternalTask,
  useDeleteExternalTask,
  useExternalTasks,
} from "../hooks/useExternalTasks";

export default function TaskBoardPage() {
  const navigate = useNavigate();
  const { data: tasks = [], isLoading } = useExternalTasks();
  const createMut = useCreateExternalTask();
  const deleteMut = useDeleteExternalTask();
  const [title, setTitle] = useState("");
  const [cwd, setCwd] = useState("");

  const columns = useMemo(() => groupByState(tasks), [tasks]);

  const handleCreate = useCallback(async () => {
    if (!title.trim() || !cwd.trim()) return;
    const task = await createMut.mutateAsync({
      title: title.trim(),
      cwd: cwd.trim(),
      pluginDirs: [],
    });
    setTitle("");
    navigate(`/tasks/${task.taskId}`);
  }, [title, cwd, createMut, navigate]);

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
          <Column title="Draft" icon={<Circle size={14} />} items={columns.draft} onOpen={(id) => navigate(`/tasks/${id}`)} />
          <Column title="In progress" icon={<PlayCircle size={14} />} items={columns.inProgress} onOpen={(id) => navigate(`/tasks/${id}`)} />
          <Column
            title="Done"
            icon={<CheckCircle2 size={14} />}
            items={columns.done}
            onOpen={(id) => navigate(`/tasks/${id}`)}
            onDelete={(id) => deleteMut.mutate(id)}
          />
        </div>
      )}
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

function Column({
  title,
  icon,
  items,
  onOpen,
  onDelete,
}: {
  title: string;
  icon: React.ReactNode;
  items: ExternalTask[];
  onOpen: (taskId: string) => void;
  onDelete?: (taskId: string) => void;
}) {
  return (
    <div className="flex min-w-[220px] flex-col gap-2 rounded border border-neutral-200 bg-neutral-50 p-2" data-testid={`column-${title.toLowerCase().replace(" ", "-")}`}>
      <div className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-neutral-600">
        {icon} {title} <span className="text-neutral-400">({items.length})</span>
      </div>
      {items.length === 0 && <div className="py-1 text-xs text-neutral-400">none</div>}
      {items.map((t) => (
        <div
          key={t.taskId}
          className="flex items-start gap-2 rounded border border-neutral-200 bg-white p-2 hover:bg-blue-50"
          data-testid={`task-card-${t.taskId}`}
        >
          <button
            type="button"
            onClick={() => onOpen(t.taskId)}
            className="flex-1 text-left"
          >
            <div className="truncate text-sm font-medium">{t.title}</div>
            <div className="flex items-center gap-1 text-xs text-neutral-500">
              {t.state === "jsonl_missing" || t.state === "launch_failed" ? (
                <AlertTriangle size={12} className="text-red-500" />
              ) : null}
              {t.state}
            </div>
          </button>
          {onDelete && (
            <button
              type="button"
              onClick={() => onDelete(t.taskId)}
              className="text-xs text-neutral-400 hover:text-red-600"
              data-testid={`delete-${t.taskId}`}
              title="Remove card (does NOT delete the JSONL on disk)"
            >
              remove
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
