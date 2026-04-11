import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import type { Task, KanbanStatus } from '../../types';
import { PhaseTag } from './PhaseTag';
import { PriorityIndicator } from './PriorityIndicator';
import { IntentBadge } from './IntentBadge';
import { ComplexityIndicator } from './ComplexityIndicator';
import { CardOverflowMenu } from './CardOverflowMenu';
import { StartTaskButton } from './StartTaskButton';
import { formatRelativeTime } from '../../lib/formatTime';

interface TaskCardProps {
  task: Task;
  columnStatus?: KanbanStatus;
}

export function TaskCard({ task, columnStatus }: TaskCardProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });

  const isBacklog = columnStatus === 'backlog' || task.kanbanStatus === 'backlog';

  return (
    <div
      role="button"
      tabIndex={0}
      className="bg-white rounded-xl p-3 cursor-pointer shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-card-hover)] hover:-translate-y-px transition-all group border-0"
      onClick={() => navigate(`/tasks/${task.id}`)}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/tasks/${task.id}`)}
    >
      {/* Top: title + overflow */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-sm font-semibold text-gray-900 line-clamp-2 flex-1">
          {task.description}
        </span>
        <CardOverflowMenu
          onClose={() => updateStatus.mutate('done')}
          onCancel={() => updateStatus.mutate('cancelled')}
        />
      </div>

      {/* Middle: phase + priority + intent + complexity */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <PhaseTag phase={task.currentPhase} />
        <PriorityIndicator priority={task.priority} />
        <span className="transition-opacity duration-300"><IntentBadge intent={task.intent} /></span>
        <span className="transition-opacity duration-300"><ComplexityIndicator complexity={task.complexity} /></span>
      </div>

      {/* Bottom: time-ago + id + start button */}
      <div className="flex items-center gap-3 text-[11px] text-gray-400">
        <span>{formatRelativeTime(task.updatedAt)}</span>
        <span>#{task.id.slice(0, 7)}</span>
        <span className="flex-1" />
        {isBacklog && (
          <StartTaskButton projectId={task.projectId} taskId={task.id} />
        )}
      </div>
    </div>
  );
}
