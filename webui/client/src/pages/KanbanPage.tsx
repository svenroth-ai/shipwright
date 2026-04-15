import { useEffect, useState, useCallback, useMemo } from 'react';
import { useProjects } from '../hooks/useProjects';
import { useTasks } from '../hooks/useTasks';
import { useBoardFilters } from '../hooks/useBoardFilters';
import { ProjectTabs } from '../components/board/ProjectTabs';
import { KanbanBoard } from '../components/board/KanbanBoard';
import { FilterBar } from '../components/board/FilterBar';
import { TaskListView } from '../components/board/TaskListView';
import { CreateMenu } from '../components/board/CreateMenu';
import { NewIssueModal } from '../components/board/NewIssueModal';
import { NewPipelineModal } from '../components/board/NewPipelineModal';
import { PreviewButton } from '../components/board/PreviewButton';
import { ProjectFilterChip } from '../components/board/ProjectFilterChip';
import { getStored, setStored } from '../lib/localStorage';

// Iterate 14.7.0 — P0.3 persistence key for the active project id.
// `null` is a valid stored value meaning "All Projects" (P0.2).
const ACTIVE_PROJECT_STORAGE_KEY = 'shipwright.activeProjectId';

export default function KanbanPage() {
  // Iterate 14.7.0 — P0.3: read the last active project id from
  // localStorage as the initial state so F5 preserves the selection.
  // Falls back to null (All Projects), which is now a valid state
  // after P0.2 removed the forced-redirect effect.
  const [activeProjectId, setActiveProjectId] = useState<string | null>(
    () => getStored<string | null>(ACTIVE_PROJECT_STORAGE_KEY, null),
  );
  const [showNewIssue, setShowNewIssue] = useState(false);
  const [showNewPipeline, setShowNewPipeline] = useState(false);
  const { data: projects = [] } = useProjects();
  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;

  // Iterate 14.7.2 — All-Projects multi-select filter. Empty set
  // means "no filter, show all". Only relevant when activeProjectId
  // is null. Reset on every toggle into single-project mode so the
  // chip doesn't silently restrict anything unexpectedly.
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<string>>(
    () => new Set(),
  );
  const showProjectStrip = activeProjectId === null;
  useEffect(() => {
    if (activeProjectId !== null && selectedProjectIds.size > 0) {
      setSelectedProjectIds(new Set());
    }
  }, [activeProjectId, selectedProjectIds.size]);

  const toggleProjectFilter = useCallback((projectId: string) => {
    setSelectedProjectIds((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
  }, []);
  const clearProjectFilter = useCallback(() => {
    setSelectedProjectIds(new Set());
  }, []);

  // Iterate 14.7.0 — P0.2: DO NOT auto-select first project when
  // activeProjectId is null. Null is a valid "All Projects" state.
  // Iterate 14.7.0 — P0.3 edge case: if the stored id no longer
  // matches any project (project was deleted), fall back to null
  // (All Projects). This only runs after projects load, so the
  // initial localStorage read isn't clobbered on first mount.
  useEffect(() => {
    if (activeProjectId && projects.length > 0 && !projects.find((p) => p.id === activeProjectId)) {
      setActiveProjectId(null);
    }
  }, [activeProjectId, projects]);

  // Iterate 14.7.0 — P0.3: persist every selection change to
  // localStorage so the next reload picks it back up.
  const handleSelectProject = useCallback((id: string | null) => {
    setActiveProjectId(id);
    setStored(ACTIVE_PROJECT_STORAGE_KEY, id);
  }, []);

  const { data: tasks = [], isLoading, isError, refetch } = useTasks(activeProjectId ?? undefined);
  const filters = useBoardFilters();
  // Iterate 14.7.2 — apply the project multi-select filter BEFORE the
  // phase/priority filters so the card count reflects both.
  const projectFilteredTasks = useMemo(() => {
    if (!showProjectStrip || selectedProjectIds.size === 0) return tasks;
    return tasks.filter((t) => selectedProjectIds.has(t.projectId));
  }, [tasks, showProjectStrip, selectedProjectIds]);
  const filteredTasks = filters.filterTasks(projectFilteredTasks);

  // Iterate 14.4 — Linear-style letter shortcuts for the create menu.
  //   c        → New Task
  //   Shift+C  → New Pipeline
  // Replaces the old Ctrl+Shift+N binding (Chrome Incognito collides at OS
  // level). Both shortcuts are guarded against editable-element focus and
  // already-open modals.
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable)
    ) {
      return;
    }
    if (showNewIssue || showNewPipeline) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key === 'C' && e.shiftKey) {
      e.preventDefault();
      setShowNewPipeline(true);
      return;
    }
    if (e.key === 'c' && !e.shiftKey) {
      e.preventDefault();
      setShowNewIssue(true);
    }
  }, [showNewIssue, showNewPipeline]);

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
          onSelect={handleSelectProject}
        />
        <div className="flex items-center gap-2">
          {activeProject?.hasPreview === true && (
            <PreviewButton projectId={activeProject.id} />
          )}
          <CreateMenu
            onNewTask={() => setShowNewIssue(true)}
            onNewPipeline={() => setShowNewPipeline(true)}
          />
        </div>
      </div>

      {/* Filter bar */}
      <div className="px-6 py-2 border-b border-gray-100 bg-white flex items-center gap-3">
        {/* Iterate 14.7.2 — project multi-select, only in All Projects
            mode. Rendered before the generic FilterBar so it sits on
            the left of the row, next to Phase/Priority filters. */}
        {showProjectStrip && (
          <ProjectFilterChip
            projects={projects}
            selectedProjectIds={selectedProjectIds}
            onToggle={toggleProjectFilter}
            onClear={clearProjectFilter}
          />
        )}
        <div className="flex-1 min-w-0">
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
          <KanbanBoard
            tasks={filteredTasks}
            onNewTask={() => setShowNewIssue(true)}
            showProjectStrip={showProjectStrip}
          />
        )}
      </div>

      <NewIssueModal
        open={showNewIssue}
        onOpenChange={setShowNewIssue}
        activeProjectId={activeProjectId}
        projects={projects}
      />
      <NewPipelineModal
        open={showNewPipeline}
        onOpenChange={setShowNewPipeline}
      />
    </div>
  );
}
