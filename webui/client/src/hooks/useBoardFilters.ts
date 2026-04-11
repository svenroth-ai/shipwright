import { useState, useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';
import type { Task } from '../types';

export type ViewMode = 'board' | 'list';

export function useBoardFilters() {
  const [selectedPhases, setSelectedPhases] = useState<string[]>([]);
  const [selectedPriority, setSelectedPriority] = useState<string | null>(null);
  const [viewMode, setViewMode] = useLocalStorage<ViewMode>('board-view-mode', 'board');

  const togglePhase = useCallback((phase: string) => {
    setSelectedPhases((prev) =>
      prev.includes(phase) ? prev.filter((p) => p !== phase) : [...prev, phase],
    );
  }, []);

  const clearPhases = useCallback(() => setSelectedPhases([]), []);

  const clearAllFilters = useCallback(() => {
    setSelectedPhases([]);
    setSelectedPriority(null);
  }, []);

  const hasActiveFilters = selectedPhases.length > 0 || selectedPriority !== null;

  const filterTasks = useCallback(
    (tasks: Task[]): Task[] => {
      let filtered = tasks;
      if (selectedPhases.length > 0) {
        filtered = filtered.filter((t) => t.currentPhase && selectedPhases.includes(t.currentPhase));
      }
      if (selectedPriority) {
        filtered = filtered.filter((t) => t.priority === selectedPriority);
      }
      return filtered;
    },
    [selectedPhases, selectedPriority],
  );

  return useMemo(
    () => ({
      selectedPhases,
      togglePhase,
      clearPhases,
      selectedPriority,
      setPriority: setSelectedPriority,
      viewMode,
      setViewMode,
      filterTasks,
      hasActiveFilters,
      clearAllFilters,
    }),
    [selectedPhases, togglePhase, clearPhases, selectedPriority, viewMode, setViewMode, filterTasks, hasActiveFilters, clearAllFilters],
  );
}
