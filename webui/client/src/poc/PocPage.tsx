import { useParams, useSearchParams } from 'react-router-dom';
import { useTasks } from '../hooks/useTasks';
import { PocChatPanel } from './PocChatPanel';

/**
 * PoC entry at /poc-chat/:taskId — renders assistant-ui primitives
 * against the same task data source our production ChatPanel uses.
 * Side-by-side comparison lives at /tasks/:taskId (current) vs
 * /poc-chat/:taskId (PoC). No impact on production routes.
 */
export default function PocPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [params] = useSearchParams();
  const { data: tasks = [] } = useTasks();
  const task = tasks.find((t) => t.id === taskId);

  if (!task) {
    return (
      <div className="p-6 text-sm text-gray-500">
        <p>PoC: task {taskId} not found.</p>
        <p className="text-xs mt-2">
          Open the production view first to confirm the task exists, then come back.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-4 py-2 bg-amber-50 text-xs text-amber-900">
        <strong>PoC route</strong> — assistant-ui rendering of task{' '}
        <code>{task.id}</code> ({task.title}).{' '}
        {params.get('compare') === '1' && 'Compare with /tasks/:id.'}
      </div>
      <div className="flex-1 min-h-0">
        <PocChatPanel projectId={task.projectId} taskId={task.id} />
      </div>
    </div>
  );
}
