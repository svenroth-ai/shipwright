import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import type { Task } from '../../types';
import { StatusIcon } from './StatusIcon';
import { PhaseTag } from './PhaseTag';
import { PriorityIndicator } from './PriorityIndicator';
import { CardOverflowMenu } from './CardOverflowMenu';
import { EditTaskModal } from './EditTaskModal';
import { formatRelativeTime } from '../../lib/formatTime';

interface TaskListRowProps {
  task: Task;
}

export function TaskListRow({ task }: TaskListRowProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });

  const isBacklog = task.kanbanStatus === 'backlog';

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0 group"
        onClick={() => navigate(`/tasks/${task.id}`)}
      >
        <td className="py-2.5 px-3">
          <StatusIcon status={task.kanbanStatus} />
        </td>
        <td className="py-2.5 px-3 text-sm text-gray-900 font-medium max-w-[300px] truncate">
          {task.title}
        </td>
        <td className="py-2.5 px-3">
          <PhaseTag phase={task.currentPhase} />
        </td>
        <td className="py-2.5 px-3">
          <PriorityIndicator priority={task.priority} />
        </td>
        <td className="py-2.5 px-3 text-xs text-gray-400">--</td>
        <td className="py-2.5 px-3 text-xs text-gray-400 font-mono">
          {task.id.slice(0, 7)}
        </td>
        <td className="py-2.5 px-3 text-xs text-gray-400">
          {formatRelativeTime(task.updatedAt)}
        </td>
        <td className="py-2.5 px-2 w-8">
          <CardOverflowMenu
            onClose={() => updateStatus.mutate('closed')}
            onDelete={() => updateStatus.mutate('cancelled')}
            onEdit={isBacklog ? () => setEditOpen(true) : undefined}
          />
        </td>
      </tr>

      <EditTaskModal open={editOpen} onOpenChange={setEditOpen} task={task} />
    </>
  );
}
