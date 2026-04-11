import * as ScrollArea from '@radix-ui/react-scroll-area';
import { Plus } from 'lucide-react';
import type { Task, KanbanStatus } from '../../types';
import { TaskCard } from './TaskCard';

const COLUMN_STYLES: Record<KanbanStatus, { bg: string; headerColor: string; borderTop: string; countBg: string; countColor: string }> = {
  backlog: { bg: 'bg-[#f0eeec]', headerColor: 'text-gray-500', borderTop: 'border-t-[3px] border-gray-400', countBg: 'bg-gray-100', countColor: 'text-gray-500' },
  in_progress: { bg: 'bg-orange-500/[0.08]', headerColor: 'text-amber-700', borderTop: 'border-t-[3px] border-amber-600', countBg: 'bg-amber-100', countColor: 'text-amber-700' },
  in_review: { bg: 'bg-emerald-500/[0.08]', headerColor: 'text-emerald-700', borderTop: 'border-t-[3px] border-emerald-600', countBg: 'bg-emerald-100', countColor: 'text-emerald-700' },
  done: { bg: 'bg-blue-500/[0.08]', headerColor: 'text-blue-600', borderTop: 'border-t-[3px] border-blue-500', countBg: 'bg-blue-100', countColor: 'text-blue-600' },
  failed: { bg: 'bg-red-500/[0.08]', headerColor: 'text-red-600', borderTop: 'border-t-[3px] border-red-500', countBg: 'bg-red-100', countColor: 'text-red-600' },
  cancelled: { bg: 'bg-gray-500/[0.08]', headerColor: 'text-gray-500', borderTop: 'border-t-[3px] border-gray-400', countBg: 'bg-gray-100', countColor: 'text-gray-500' },
};

const COLUMN_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  in_progress: 'In Progress',
  in_review: 'In Review',
  done: 'Done',
};

interface KanbanColumnProps {
  title: string;
  tasks: Task[];
  status: KanbanStatus;
  onNewTask?: () => void;
}

export function KanbanColumn({ title, tasks, status, onNewTask }: KanbanColumnProps) {
  const style = COLUMN_STYLES[status] ?? COLUMN_STYLES.backlog;

  return (
    <div className={`min-w-[280px] w-[280px] shrink-0 flex flex-col max-h-full rounded-xl overflow-hidden ${style.bg}`}>
      <div className={`flex items-center gap-2 px-3.5 pt-3.5 pb-2.5 text-[13px] font-semibold uppercase tracking-wider ${style.headerColor} ${style.borderTop}`}>
        {title}
        <span className={`text-[11px] font-bold min-w-[20px] h-5 rounded-full flex items-center justify-center px-1.5 ${style.countBg} ${style.countColor}`}>
          {tasks.length}
        </span>
      </div>

      <ScrollArea.Root className="flex-1 overflow-hidden">
        <ScrollArea.Viewport className="h-full px-2.5 pb-3.5">
          {tasks.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-gray-400 mb-2">No tasks</p>
              {status === 'backlog' && onNewTask && (
                <button
                  onClick={onNewTask}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-500 rounded-lg border border-dashed border-gray-300 hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] transition-colors"
                >
                  <Plus size={12} /> Add task
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} columnStatus={status} />
              ))}
            </div>
          )}
        </ScrollArea.Viewport>
        <ScrollArea.Scrollbar orientation="vertical" className="w-1">
          <ScrollArea.Thumb className="bg-gray-300 rounded-full" />
        </ScrollArea.Scrollbar>
      </ScrollArea.Root>
    </div>
  );
}

export { COLUMN_LABELS };
