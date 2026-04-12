import { useEffect, useState, useCallback } from 'react';
import { useProjects } from '../hooks/useProjects';
import { useTasks } from '../hooks/useTasks';
import { useBoardFilters } from '../hooks/useBoardFilters';
import { ProjectTabs } from '../components/board/ProjectTabs';
import { KanbanBoard } from '../components/board/KanbanBoard';
import { FilterBar } from '../components/board/FilterBar';
import { TaskListView } from '../components/board/TaskListView';
import { NewIssueButton } from '../components/board/NewIssueButton';
import { NewIssueModal } from '../components/board/NewIssueModal';

export default function KanbanPage() {
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [showNewIssue, setShowNewIssue] = useState(false);
  const { data: projects = [] } = useProjects();

  // Auto-select first project when projects load and none is selected
  useEffect(() => {
    if (!activeProjectId && projects.length > 0) {
      setActiveProjectId(projects[0].id);
    }
  }, [activeProjectId, projects]);

  const { data: tasks = [], isLoading, isError, refetch } = useTasks(activeProjectId ?? undefined);
  const filters = useBoardFilters();
  const filteredTasks = filters.filterTasks(tasks);

  // Keyboard shortcut: Ctrl/Cmd+Shift+N to open new task (Ctrl+N is browser-reserved)
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'N') {
      e.preventDefault();
      setShowNewIssue(true);
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="flex flex-col h-full">
      {/* Header bar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-[var(--color-border,#e0dbd4)] bg-white">
        <ProjectTabs
          projects={projects}
          activeProjectId={activeProjectId}
          onSelect={setActiveProjectId}
        />
        <NewIssueButton onClick={() => setShowNewIssue(true)} />
      </div>

      {/* Filter bar */}
      <div className="px-6 py-2 border-b border-gray-100 bg-white">
        <FilterBar
          selectedPhases={filters.selectedPhases}
          togglePhase={filters.togglePhase}
          clearPhases={filters.clearPhases}
          selectedPriority={filters.selectedPriority}
          setPriority={filters.setPriority}
          viewMode={filters.viewMode}
          setViewMode={filters.setViewMode}
        />
      </div>

      {/* Board/List area — columns scroll internally via Radix ScrollArea */}
      <div className="flex-1 min-h-0 p-5">
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
        ) : filters.viewMode === 'list' ? (
          <TaskListView tasks={filteredTasks} />
        ) : (
          <KanbanBoard tasks={filteredTasks} onNewTask={() => setShowNewIssue(true)} />
        )}
      </div>

      <NewIssueModal
        open={showNewIssue}
        onOpenChange={setShowNewIssue}
        activeProjectId={activeProjectId}
        projects={projects}
      />
    </div>
  );
}
