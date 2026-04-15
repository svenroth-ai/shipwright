import { useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useTasks } from '../hooks/useTasks';
import { TaskHeader } from '../components/detail/TaskHeader';
import { PanelLayout } from '../components/detail/PanelLayout';
import { SmartViewer } from '../components/viewer/SmartViewer';
import { ChatPanel } from '../components/chat/ChatPanel';
import { EditTaskModal } from '../components/board/EditTaskModal';

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const { data: tasks = [], isLoading } = useTasks();
  const [editOpen, setEditOpen] = useState(false);
  // Iterate 14.7.1 — Inbox → task navigation uses `?focus=chat-bottom` to
  // hint that we should scroll the chat to the newest message on arrival.
  // ChatPanel handles the actual scroll when it sees the prop set.
  const [searchParams] = useSearchParams();
  const focusChatBottom = searchParams.get('focus') === 'chat-bottom';

  const task = tasks.find((t) => t.id === taskId);

  if (isLoading) {
    return (
      <div className="flex flex-col h-full">
        <div className="h-14 border-b bg-white animate-pulse" />
        <div className="flex-1 flex">
          <div className="w-3/5 bg-gray-50 animate-pulse" />
          <div className="w-2/5 bg-gray-50 animate-pulse" />
        </div>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3">
        <p className="text-gray-500 text-lg">Task not found</p>
        <button
          className="px-4 py-2 text-sm font-medium text-[var(--color-primary)] hover:underline"
          onClick={() => navigate('/')}
        >
          Back to Board
        </button>
      </div>
    );
  }

  const isPending = task.status === 'pending' || task.kanbanStatus === 'backlog';

  return (
    <div className="flex flex-col h-full">
      <TaskHeader task={task} onEdit={isPending ? () => setEditOpen(true) : undefined} />
      <PanelLayout
        leftPanel={
          <ChatPanel
            projectId={task.projectId}
            taskId={task.id}
            focusBottomOnMount={focusChatBottom}
          />
        }
        rightPanel={<SmartViewer projectId={task.projectId} />}
      />
      <EditTaskModal open={editOpen} onOpenChange={setEditOpen} task={task} />
    </div>
  );
}
