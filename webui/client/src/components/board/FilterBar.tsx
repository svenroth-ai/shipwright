import { PhaseFilter } from './PhaseFilter';
import { PriorityFilter } from './PriorityFilter';
import { ViewToggle } from './ViewToggle';
import { FilterChip } from './FilterChip';
import type { ViewMode } from '../../hooks/useBoardFilters';

interface FilterBarProps {
  selectedPhases: string[];
  togglePhase: (phase: string) => void;
  clearPhases: () => void;
  selectedPriority: string | null;
  setPriority: (p: string | null) => void;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
}

export function FilterBar({
  selectedPhases,
  togglePhase,
  clearPhases,
  selectedPriority,
  setPriority,
  viewMode,
  setViewMode,
}: FilterBarProps) {
  return (
    <div className="flex items-center gap-3">
      <PhaseFilter selectedPhases={selectedPhases} onToggle={togglePhase} onClear={clearPhases} />
      <PriorityFilter selectedPriority={selectedPriority} onSelect={setPriority} />

      {/* Active filter chips */}
      {(selectedPhases.length > 0 || selectedPriority) && (
        <div className="flex items-center gap-1.5 ml-1">
          {selectedPhases.map((phase) => (
            <FilterChip key={phase} label={phase} onRemove={() => togglePhase(phase)} />
          ))}
          {selectedPriority && (
            <FilterChip label={selectedPriority} onRemove={() => setPriority(null)} />
          )}
        </div>
      )}

      <div className="ml-auto">
        <ViewToggle viewMode={viewMode} onChange={setViewMode} />
      </div>
    </div>
  );
}
