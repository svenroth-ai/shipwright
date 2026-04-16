import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, MoreVertical, CheckCircle, Pencil, Trash2, Play, FileText, Pause } from 'lucide-react';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Popover from '@radix-ui/react-popover';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import { useStartTask } from '../../hooks/useStartTask';
import { useResumeTask } from '../../hooks/useResumeTask';
import type { Task } from '../../types';
import { PhaseTag } from '../board/PhaseTag';
import { PriorityIndicator } from '../board/PriorityIndicator';
import { StatusIcon } from '../board/StatusIcon';
import { formatRelativeTime } from '../../lib/formatTime';

interface TaskHeaderProps {
  task: Task;
  onEdit?: () => void;
}

const STATUS_LABELS: Record<string, string> = {
  backlog: 'Backlog',
  in_progress: 'In Progress',
  in_review: 'In Review',
  done: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export function TaskHeader({ task, onEdit }: TaskHeaderProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const startTask = useStartTask();
  const resumeTask = useResumeTask();

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}/status`, { status }),
    onSuccess: (_data, status) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
      // After delete (cancelled) or close, the task detail view no longer
      // makes sense — redirect back to the kanban board.
      if (status === 'cancelled' || status === 'closed') {
        navigate('/');
      }
    },
  });

  const isPending = task.status === 'pending' || task.kanbanStatus === 'backlog';

  // Iterate 14.11 — interrupted-task pause indicator + Resume button in
  // the detail header. Same derivation used by TaskCard (board, 14.7.0)
  // and AskUserCard (chat, 14.10): orphaned status + resumable
  // orphanReason + captured claudeSessionId. Closes the third visibility
  // gap — opening an interrupted task's detail page now surfaces the
  // affordance regardless of whether a pending AskUserCard exists.
  const isInterrupted =
    task.status === 'orphaned' &&
    (task.orphanReason === 'stale_on_startup' ||
      task.orphanReason === 'user_interrupted') &&
    !!task.claudeSessionId;

  return (
    <header className="flex items-start gap-4 px-6 py-3.5 border-b border-[#e0dbd4] bg-white">
      {/* Left: back, title, status */}
      <div className="flex-1 min-w-0">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 transition-colors mb-1.5"
        >
          <ArrowLeft size={14} />
          Back to Board
        </button>

        {/* Title row */}
        <div className="flex items-center gap-2.5 flex-wrap mb-2">
          <h1 className="text-lg font-semibold text-gray-900 tracking-[-0.3px]">{task.title}</h1>
          <PhaseTag phase={task.currentPhase} />
          <PriorityIndicator priority={task.priority} />
        </div>

        {/* Status line + Show Description */}
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <StatusIcon status={task.kanbanStatus} />
          <span className="font-medium">{STATUS_LABELS[task.kanbanStatus] ?? task.kanbanStatus}</span>
          <span>&middot;</span>
          <span>{formatRelativeTime(task.updatedAt)}</span>

          {task.description && (
            <>
              <span>&middot;</span>
              <Popover.Root>
                <Popover.Trigger asChild>
                  <button className="flex items-center gap-1 text-[var(--color-primary)] hover:underline cursor-pointer">
                    <FileText size={11} />
                    Show Description
                  </button>
                </Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content
                    className="bg-white rounded-lg shadow-[var(--shadow-card)] border border-[#e0dbd4] p-3 max-w-[400px] z-50"
                    sideOffset={6}
                    align="start"
                  >
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{task.description}</p>
                    <Popover.Arrow className="fill-white" />
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            </>
          )}
        </div>

        {/* Iterate 14.11 — pause indicator + Resume button for interrupted
            tasks. Renders inline below the status row so the user always
            sees the affordance on the detail page, not only when a
            pending AskUserCard happens to be in the chat history. */}
        {isInterrupted && (
          <div
            data-testid="header-pause-indicator"
            className="flex items-center gap-2 mt-2 px-3 py-2 rounded bg-amber-50 border border-amber-200"
          >
            <Pause size={16} className="text-amber-700 shrink-0" />
            <span className="text-sm text-amber-900 flex-1">
              Task interrupted — resume to continue
            </span>
            <button
              type="button"
              data-testid="header-resume-button"
              disabled={resumeTask.isPending}
              onClick={() =>
                resumeTask.mutate({ projectId: task.projectId, taskId: task.id })
              }
              className="px-3 py-1 text-xs font-semibold bg-amber-700 text-white rounded hover:bg-amber-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {resumeTask.isPending ? 'Resuming…' : 'Resume'}
            </button>
          </div>
        )}
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

                  {onEdit && (
                    <DropdownMenu.Item
                      className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 rounded-md outline-none"
                      onSelect={onEdit}
                    >
                      <Pencil size={15} className="text-gray-500" /> Edit task
                    </DropdownMenu.Item>
                  )}

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
