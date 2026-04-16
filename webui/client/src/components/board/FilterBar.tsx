import { PhaseFilter } from './PhaseFilter';
import { ViewToggle } from './ViewToggle';
import { FilterChip } from './FilterChip';
import type { ViewMode } from '../../hooks/useBoardFilters';

interface FilterBarProps {
  selectedPhases: string[];
  togglePhase: (phase: string) => void;
  clearPhases: () => void;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
}

export function FilterBar({
  selectedPhases,
  togglePhase,
  clearPhases,
  viewMode,
  setViewMode,
}: FilterBarProps) {
  return (
    <div className="flex items-center gap-3">
      <PhaseFilter selectedPhases={selectedPhases} onToggle={togglePhase} onClear={clearPhases} />

      {/* Active filter chips */}
      {selectedPhases.length > 0 && (
        <div className="flex items-center gap-1.5 ml-1">
          {selectedPhases.map((phase) => (
            <FilterChip key={phase} label={phase} onRemove={() => togglePhase(phase)} />
          ))}
        </div>
      )}

      <div className="ml-auto">
        <ViewToggle viewMode={viewMode} onChange={setViewMode} />
      </div>
    </div>
  );
}
