import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import type { Task } from '../../types';
import { PhaseTag } from './PhaseTag';
import { PriorityIndicator } from './PriorityIndicator';
import { CardOverflowMenu } from './CardOverflowMenu';

interface TaskCardProps {
  task: Task;
}

export function TaskCard({ task }: TaskCardProps) {
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

  return (
    <div
      role="button"
      tabIndex={0}
      className="bg-white rounded-[10px] p-3 cursor-pointer shadow-[0_1px_3px_rgba(0,0,0,0.06)] hover:shadow-[0_4px_16px_rgba(0,0,0,0.12)] hover:-translate-y-px transition-all group"
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

      {/* Middle: phase + priority */}
      <div className="flex items-center gap-2 mb-2">
        <PhaseTag phase={task.currentPhase} />
        <PriorityIndicator priority={task.priority} />
      </div>

      {/* Bottom: meta */}
      <div className="flex items-center gap-3 text-[11px] text-gray-400">
        <span>Tests: --</span>
        <span>#{task.id.slice(0, 7)}</span>
      </div>
    </div>
  );
}
