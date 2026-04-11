import { useParams } from 'react-router-dom';

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Task {taskId}</h1>
    </div>
  );
}
