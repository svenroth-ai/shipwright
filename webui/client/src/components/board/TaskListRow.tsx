import { useNavigate } from 'react-router-dom';
import type { Task } from '../../types';
import { StatusIcon } from './StatusIcon';
import { PhaseTag } from './PhaseTag';
import { PriorityIndicator } from './PriorityIndicator';
import { formatRelativeTime } from '../../lib/formatTime';

interface TaskListRowProps {
  task: Task;
}

export function TaskListRow({ task }: TaskListRowProps) {
  const navigate = useNavigate();

  return (
    <tr
      className="hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-b-0"
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
    </tr>
  );
}
