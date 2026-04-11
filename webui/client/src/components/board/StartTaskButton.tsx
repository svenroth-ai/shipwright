import { Play } from 'lucide-react';
import { useStartTask } from '../../hooks/useStartTask';

interface StartTaskButtonProps {
  projectId: string;
  taskId: string;
}

export function StartTaskButton({ projectId, taskId }: StartTaskButtonProps) {
  const startTask = useStartTask();

  return (
    <button
      className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-white bg-green-600 rounded hover:bg-green-700 disabled:opacity-50"
      onClick={(e) => {
        e.stopPropagation();
        startTask.mutate({ projectId, taskId });
      }}
      disabled={startTask.isPending}
    >
      <Play size={12} />
      Start
    </button>
  );
}
