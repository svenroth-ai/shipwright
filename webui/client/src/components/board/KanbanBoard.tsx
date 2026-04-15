import { useState, useMemo } from 'react';
import type { Task, KanbanStatus } from '../../types';
import { KanbanColumn, COLUMN_LABELS } from './KanbanColumn';

const VISIBLE_COLUMNS: KanbanStatus[] = ['backlog', 'in_progress', 'in_review', 'done'];
const MAX_DONE_VISIBLE = 10;

interface KanbanBoardProps {
  tasks: Task[];
  onNewTask?: () => void;
  // Iterate 14.7.2 — when true, cards render a colored project strip
  // on the left edge. Threaded from KanbanPage based on activeProjectId.
  showProjectStrip?: boolean;
}

export function KanbanBoard({ tasks, onNewTask, showProjectStrip = false }: KanbanBoardProps) {
  const [showAllDone, setShowAllDone] = useState(false);

  const grouped = useMemo(() => {
    const buckets: Record<KanbanStatus, Task[]> = {
      backlog: [],
      in_progress: [],
      in_review: [],
      done: [],
      failed: [],
      cancelled: [],
      interrupted: [],
    };

    for (const task of tasks) {
      const bucket = buckets[task.kanbanStatus];
      if (bucket) bucket.push(task);
    }

    // Iterate 14.7.0 — interrupted tasks live visually in the
    // "In Progress" column alongside running tasks. The TaskCard
    // itself adds a pause icon + Resume/Cancel affordances.
    if (buckets.interrupted.length > 0) {
      buckets.in_progress = [...buckets.interrupted, ...buckets.in_progress];
    }

    return buckets;
  }, [tasks]);

  return (
    <div className="flex gap-4 overflow-x-auto h-full">
      {VISIBLE_COLUMNS.map((status) => {
        let columnTasks = grouped[status];

        if (status === 'done' && !showAllDone && columnTasks.length > MAX_DONE_VISIBLE) {
          const total = columnTasks.length;
          columnTasks = columnTasks.slice(0, MAX_DONE_VISIBLE);

          return (
            <div key={status} className="flex flex-col min-w-[280px] w-[280px] shrink-0 max-h-full">
              <KanbanColumn
                title={COLUMN_LABELS[status]}
                tasks={columnTasks}
                status={status}
                onNewTask={onNewTask}
                showProjectStrip={showProjectStrip}
              />
              <button
                className="flex items-center justify-center px-3.5 py-2.5 text-[13px] font-semibold text-blue-600 cursor-pointer rounded-[10px] bg-blue-500/[0.06] hover:bg-blue-500/[0.12] transition-colors mt-1"
                onClick={() => setShowAllDone(true)}
              >
                Show all ({total})
              </button>
            </div>
          );
        }

        return (
          <KanbanColumn
            key={status}
            title={COLUMN_LABELS[status]}
            tasks={columnTasks}
            status={status}
            showProjectStrip={showProjectStrip}
          />
        );
      })}
    </div>
  );
}
