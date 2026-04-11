import { useState } from 'react';
import { useProjects } from '../hooks/useProjects';
import { useTasks } from '../hooks/useTasks';
import { ProjectTabs } from '../components/board/ProjectTabs';
import { KanbanBoard } from '../components/board/KanbanBoard';
import { NewIssueButton } from '../components/board/NewIssueButton';

export default function KanbanPage() {
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const { data: projects = [] } = useProjects();
  const { data: tasks = [], isLoading, isError, refetch } = useTasks(activeProjectId ?? undefined);

  return (
    <div className="flex flex-col h-full">
      {/* Header bar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--color-border,#e0dbd4)] bg-white">
        <ProjectTabs
          projects={projects}
          activeProjectId={activeProjectId}
          onSelect={setActiveProjectId}
        />
        <div className="flex items-center gap-2">
          {/* Filter bar slot — Section 06 */}
          <NewIssueButton onClick={() => {/* Section 05 wires modal */}} />
        </div>
      </div>

      {/* Board area */}
      <div className="flex-1 p-5 overflow-hidden">
        {isLoading ? (
          <div className="flex gap-4 h-full">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="min-w-[280px] w-[280px] shrink-0 bg-gray-100/50 rounded-xl animate-pulse" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <p className="text-gray-500">Failed to load tasks</p>
            <button
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90"
              onClick={() => refetch()}
            >
              Retry
            </button>
          </div>
        ) : (
          <KanbanBoard tasks={tasks} />
        )}
      </div>
    </div>
  );
}
