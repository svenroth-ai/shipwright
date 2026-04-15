import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Pause } from 'lucide-react';
import { apiPatch } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import type { Task, KanbanStatus } from '../../types';
import { PhaseTag } from './PhaseTag';
import { PriorityIndicator } from './PriorityIndicator';
import { IntentBadge } from './IntentBadge';
import { ComplexityIndicator } from './ComplexityIndicator';
import { CardOverflowMenu } from './CardOverflowMenu';
import { EditTaskModal } from './EditTaskModal';
import { StartTaskButton } from './StartTaskButton';
import { useResumeTask } from '../../hooks/useResumeTask';
import { formatRelativeTime } from '../../lib/formatTime';
import { getProjectColor } from '../../lib/projectColor';

interface TaskCardProps {
  task: Task;
  columnStatus?: KanbanStatus;
  // Iterate 14.7.2 — when true, renders a colored left-edge strip
  // derived from the projectId hash and switches the phase tag to
  // monochrome. Controlled from KanbanPage when activeProjectId is
  // null (the All Projects view).
  showProjectStrip?: boolean;
}

export function TaskCard({ task, columnStatus, showProjectStrip = false }: TaskCardProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const resumeTask = useResumeTask();

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      apiPatch(`/projects/${task.projectId}/tasks/${task.id}/status`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.byProject(task.projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all });
    },
  });

  const isBacklog = columnStatus === 'backlog' || task.kanbanStatus === 'backlog';
  // Iterate 14.7.0 — interrupted tasks (server restart killed the
  // Claude process while it was running) render with a pause icon
  // and a Resume/Cancel action row. They live visually in the
  // in_progress column.
  const isInterrupted = task.kanbanStatus === 'interrupted';

  // Iterate 14.7.2 — only render the strip when we're in All Projects
  // mode AND the task carries a projectId. Guards against edge cases
  // where a test or legacy event lacks the field.
  const stripVisible = showProjectStrip && Boolean(task.projectId);
  const stripColor = stripVisible
    ? getProjectColor(task.projectId).hslStripe
    : undefined;

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        className={`bg-white rounded-xl p-3 cursor-pointer shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-card-hover)] hover:-translate-y-px transition-all group border-0 relative overflow-hidden ${
          stripVisible ? 'pl-4' : ''
        }`}
        onClick={() => navigate(`/tasks/${task.id}`)}
        onKeyDown={(e) => e.key === 'Enter' && navigate(`/tasks/${task.id}`)}
      >
        {stripVisible && (
          <span
            data-testid="project-strip"
            aria-hidden="true"
            className="absolute left-0 top-0 bottom-0 w-1"
            style={{ backgroundColor: stripColor }}
          />
        )}
        {/* Top: title + overflow */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <span className="text-sm font-semibold text-gray-900 line-clamp-2 flex-1">
            {task.title}
          </span>
          <div className="flex items-center gap-1">
            {isInterrupted && (
              <span
                className="text-amber-500"
                title="Task was interrupted by server restart. Click Resume to continue."
                aria-label="Task interrupted"
                data-testid="interrupted-pause-icon"
              >
                <Pause size={14} fill="currentColor" />
              </span>
            )}
            <CardOverflowMenu
              onClose={() => updateStatus.mutate('closed')}
              onDelete={() => updateStatus.mutate('cancelled')}
              onEdit={isBacklog ? () => setEditOpen(true) : undefined}
            />
          </div>
        </div>

        {/* Middle: phase + priority + intent + complexity */}
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <PhaseTag phase={task.currentPhase} monochrome={showProjectStrip} />
          <PriorityIndicator priority={task.priority} />
          <span className="transition-opacity duration-300"><IntentBadge intent={task.intent} /></span>
          <span className="transition-opacity duration-300"><ComplexityIndicator complexity={task.complexity} /></span>
        </div>

        {/* Bottom: time-ago + id + start button */}
        <div className="flex items-center gap-3 text-[11px] text-gray-400">
          <span>{formatRelativeTime(task.updatedAt)}</span>
          <span>#{task.id.slice(0, 7)}</span>
          <span className="flex-1" />
          {isBacklog && (
            <StartTaskButton projectId={task.projectId} taskId={task.id} />
          )}
        </div>

        {/* Iterate 14.7.0 — Resume / Cancel action row for interrupted
            tasks. Rendered below the existing card body so the layout
            for running tasks is unchanged. Both buttons stop event
            propagation to avoid navigating into the task detail page. */}
        {isInterrupted && (
          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-gray-100">
            <button
              type="button"
              data-testid="resume-task-button"
              disabled={resumeTask.isPending}
              onClick={(e) => {
                e.stopPropagation();
                resumeTask.mutate({ projectId: task.projectId, taskId: task.id });
              }}
              className="flex-1 px-2.5 py-1 text-[11px] font-semibold text-white bg-amber-500 rounded-md hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {resumeTask.isPending ? 'Resuming…' : 'Resume'}
            </button>
            <button
              type="button"
              data-testid="cancel-interrupted-button"
              onClick={(e) => {
                e.stopPropagation();
                updateStatus.mutate('cancelled');
              }}
              className="flex-1 px-2.5 py-1 text-[11px] font-semibold text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      <EditTaskModal
        open={editOpen}
        onOpenChange={setEditOpen}
        task={task}
      />
    </>
  );
}
