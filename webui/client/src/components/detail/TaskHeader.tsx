import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import type { Task } from '../../types';
import { PhaseTag } from '../board/PhaseTag';
import { PriorityIndicator } from '../board/PriorityIndicator';
import { StatusIcon } from '../board/StatusIcon';

interface TaskHeaderProps {
  task: Task;
}

const STATUS_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  in_progress: 'In Progress',
  in_review: 'In Review',
  done: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export function TaskHeader({ task }: TaskHeaderProps) {
  const navigate = useNavigate();

  return (
    <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-200 bg-white flex-wrap">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
      >
        <ArrowLeft size={16} />
        Back to Board
      </button>

      <div className="w-px h-5 bg-gray-200" />

      <h1 className="text-lg font-semibold text-gray-900">{task.description}</h1>

      <div className="flex items-center gap-2 ml-auto flex-wrap">
        <PhaseTag phase={task.currentPhase} />
        <PriorityIndicator priority={task.priority} />
        <div className="flex items-center gap-1.5 text-sm text-gray-500">
          <StatusIcon status={task.kanbanStatus} />
          <span>{STATUS_LABELS[task.kanbanStatus] ?? task.kanbanStatus}</span>
        </div>
      </div>
    </div>
  );
}
