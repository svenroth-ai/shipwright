import { useState } from 'react';
import { Play, AlertCircle } from 'lucide-react';
import { useStartTask } from '../../hooks/useStartTask';

interface StartTaskButtonProps {
  projectId: string;
  taskId: string;
}

export function StartTaskButton({ projectId, taskId }: StartTaskButtonProps) {
  const startTask = useStartTask();
  const [error, setError] = useState<string | null>(null);

  function handleStart(e: React.MouseEvent) {
    e.stopPropagation();
    setError(null);
    startTask.mutate(
      { projectId, taskId },
      {
        onError: (err) => {
          setError(err instanceof Error ? err.message : 'Failed to start task');
        },
      }
    );
  }

  return (
    <div className="flex items-center gap-1">
      <button
        className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-white bg-green-600 rounded hover:bg-green-700 disabled:opacity-50"
        onClick={handleStart}
        disabled={startTask.isPending}
      >
        <Play size={12} />
        {startTask.isPending ? 'Starting...' : 'Start'}
      </button>
      {error && (
        <span className="flex items-center gap-1 text-[10px] text-red-500" title={error}>
          <AlertCircle size={10} />
        </span>
      )}
    </div>
  );
}
