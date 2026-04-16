import { useState, useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';
import type { Task } from '../types';

export type ViewMode = 'board' | 'list';

export function useBoardFilters() {
  const [selectedPhases, setSelectedPhases] = useState<string[]>([]);
  const [viewMode, setViewMode] = useLocalStorage<ViewMode>('board-view-mode', 'board');

  const togglePhase = useCallback((phase: string) => {
    setSelectedPhases((prev) =>
      prev.includes(phase) ? prev.filter((p) => p !== phase) : [...prev, phase],
    );
  }, []);

  const clearPhases = useCallback(() => setSelectedPhases([]), []);

  const clearAllFilters = useCallback(() => {
    setSelectedPhases([]);
  }, []);

  const hasActiveFilters = selectedPhases.length > 0;

  const filterTasks = useCallback(
    (tasks: Task[]): Task[] => {
      if (selectedPhases.length === 0) return tasks;
      return tasks.filter((t) => t.currentPhase && selectedPhases.includes(t.currentPhase));
    },
    [selectedPhases],
  );

  return useMemo(
    () => ({
      selectedPhases,
      togglePhase,
      clearPhases,
      viewMode,
      setViewMode,
      filterTasks,
      hasActiveFilters,
      clearAllFilters,
    }),
    [selectedPhases, togglePhase, clearPhases, viewMode, setViewMode, filterTasks, hasActiveFilters, clearAllFilters],
  );
}
