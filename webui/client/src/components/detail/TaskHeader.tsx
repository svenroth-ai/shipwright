import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, MoreVertical, CheckCircle, Pencil, Trash2, Play, Check, X } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import { useStartTask } from '../../hooks/useStartTask';
import type { Task } from '../../types';
import { PhaseTag } from '../board/PhaseTag';
import { PriorityIndicator } from '../board/PriorityIndicator';
import { StatusIcon } from '../board/StatusIcon';
import { formatRelativeTime } from '../../lib/formatTime';

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
  const queryClient = useQueryClient();
  const startTask = useStartTask();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(task.title);
  const [editDesc, setEditDesc] = useState(task.description);

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });

  const updateDetails = useMutation({
    mutationFn: (data: { title?: string; description?: string }) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}/description`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
      setIsEditing(false);
    },
  });

  const isPending = task.status === 'pending' || task.kanbanStatus === 'backlog';

  function handleStartEdit() {
    setEditTitle(task.title);
    setEditDesc(task.description);
    setIsEditing(true);
  }

  function handleSaveEdit() {
    const t = editTitle.trim();
    const d = editDesc.trim();
    if (!t) return;
    const patch: { title?: string; description?: string } = {};
    if (t !== task.title) patch.title = t;
    if (d !== task.description) patch.description = d;
    if (Object.keys(patch).length > 0) {
      updateDetails.mutate(patch);
    } else {
      setIsEditing(false);
    }
  }

  function handleCancelEdit() {
    setEditTitle(task.title);
    setEditDesc(task.description);
    setIsEditing(false);
  }

  return (
    <header className="flex items-start gap-4 px-6 py-3.5 border-b border-[#e0dbd4] bg-white">
      {/* Left: back, title, description, status */}
      <div className="flex-1 min-w-0">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors mb-1.5"
        >
          <ArrowLeft size={14} />
          Back to Board
        </button>

        {isEditing ? (
          <div className="space-y-2 mb-1">
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveEdit();
                  if (e.key === 'Escape') handleCancelEdit();
                }}
                className="text-lg font-semibold text-gray-900 bg-gray-50 border border-gray-300 rounded-lg px-2 py-0.5 flex-1 min-w-0 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
                placeholder="Task title"
              />
              <button onClick={handleSaveEdit} className="p-1 text-green-600 hover:bg-green-50 rounded" title="Save">
                <Check size={16} />
              </button>
              <button onClick={handleCancelEdit} className="p-1 text-gray-400 hover:bg-gray-100 rounded" title="Cancel">
                <X size={16} />
              </button>
            </div>
            <textarea
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSaveEdit();
                if (e.key === 'Escape') handleCancelEdit();
              }}
              rows={3}
              className="w-full text-sm text-gray-600 bg-gray-50 border border-gray-300 rounded-lg px-2 py-1 outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)] resize-none"
              placeholder="Description (optional)"
            />
          </div>
        ) : (
          <>
            {/* Title row */}
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-lg font-semibold text-gray-900 tracking-[-0.3px]">{task.title}</h1>
              <PhaseTag phase={task.currentPhase} />
              <PriorityIndicator priority={task.priority} />
            </div>

            {/* Description (smaller, lighter) */}
            {task.description && (
              <p className="text-sm text-gray-500 font-normal mt-0.5 line-clamp-2">{task.description}</p>
            )}
          </>
        )}

        {/* Status line */}
        <div className="flex items-center gap-1.5 mt-1 text-xs text-gray-500">
          <StatusIcon status={task.kanbanStatus} />
          <span className="font-medium">{STATUS_LABELS[task.kanbanStatus] ?? task.kanbanStatus}</span>
          <span>&middot;</span>
          <span>{formatRelativeTime(task.updatedAt)}</span>
        </div>
      </div>

      {/* Right: three-dot menu */}
      <div className="pt-5">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              aria-label="Task actions"
              className="w-8 h-8 flex items-center justify-center rounded-lg border border-[#e0dbd4] bg-white text-gray-500 hover:bg-[#ede8e1] hover:text-gray-900 transition-all"
            >
              <MoreVertical size={16} />
            </button>
          </DropdownMenu.Trigger>

          <DropdownMenu.Portal>
            <DropdownMenu.Content
              className="bg-white rounded-lg shadow-[var(--shadow-card)] border border-[#e0dbd4] p-1 min-w-[160px] z-50"
              sideOffset={4}
              align="end"
            >
              {isPending && (
                <>
                  <DropdownMenu.Item
                    className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 rounded-md outline-none"
                    onSelect={() => startTask.mutate({ projectId: task.projectId, taskId: task.id })}
                  >
                    <Play size={15} className="text-green-600" /> Start task
                  </DropdownMenu.Item>

                  <DropdownMenu.Item
                    className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 rounded-md outline-none"
                    onSelect={handleStartEdit}
                  >
                    <Pencil size={15} className="text-gray-500" /> Edit details
                  </DropdownMenu.Item>

                  <DropdownMenu.Separator className="h-px bg-[#e0dbd4] my-1" />
                </>
              )}

              <DropdownMenu.Item
                className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 rounded-md outline-none"
                onSelect={() => updateStatus.mutate('closed')}
              >
                <CheckCircle size={15} className="text-gray-500" /> Close task
              </DropdownMenu.Item>

              <DropdownMenu.Separator className="h-px bg-[#e0dbd4] my-1" />

              <DropdownMenu.Item
                className="flex items-center gap-2 px-3 py-2 text-sm text-red-600 cursor-pointer hover:bg-red-50 rounded-md outline-none"
                onSelect={() => updateStatus.mutate('cancelled')}
              >
                <Trash2 size={15} /> Delete
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>
  );
}
