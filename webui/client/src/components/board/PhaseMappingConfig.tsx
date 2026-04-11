import { useState } from 'react';
import type { KanbanStatus } from '../../types';
import { DEFAULT_PHASE_MAPPING, PIPELINE_PHASES, KANBAN_COLUMNS } from '../../lib/phaseMapping';

const PHASE_COLORS: Record<string, string> = {
  project: 'bg-gray-400',
  design: 'bg-purple-500',
  plan: 'bg-blue-500',
  build: 'bg-orange-500',
  test: 'bg-green-500',
  deploy: 'bg-teal-500',
  done: 'bg-gray-600',
};

interface PhaseMappingConfigProps {
  mapping: Record<string, KanbanStatus>;
  onSave: (mapping: Record<string, KanbanStatus>) => void;
}

export function PhaseMappingConfig({ mapping: initialMapping, onSave }: PhaseMappingConfigProps) {
  const [localMapping, setLocalMapping] = useState<Record<string, KanbanStatus>>({ ...initialMapping });

  function handleChange(phase: string, status: KanbanStatus) {
    setLocalMapping((prev) => ({ ...prev, [phase]: status }));
  }

  function handleReset() {
    setLocalMapping({ ...DEFAULT_PHASE_MAPPING });
  }

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-gray-700 mb-2">Phase to Column Mapping</div>
      <div className="space-y-2">
        {PIPELINE_PHASES.map((phase) => (
          <div key={phase} className="flex items-center gap-3">
            <span className={`w-2.5 h-2.5 rounded-full ${PHASE_COLORS[phase] ?? 'bg-gray-400'}`} />
            <span className="text-sm capitalize w-20">{phase}</span>
            <select
              value={localMapping[phase] ?? 'backlog'}
              onChange={(e) => handleChange(phase, e.target.value as KanbanStatus)}
              className="flex-1 px-2 py-1 border border-gray-200 rounded text-sm"
              data-testid={`mapping-${phase}`}
            >
              {KANBAN_COLUMNS.map((col) => (
                <option key={col.id} value={col.id}>{col.label}</option>
              ))}
            </select>
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-2">
        <button
          className="text-xs text-gray-500 hover:text-gray-700 underline"
          onClick={handleReset}
        >
          Reset to defaults
        </button>
        <button
          className="ml-auto px-3 py-1.5 text-xs font-medium text-white bg-[var(--color-primary)] rounded hover:opacity-90"
          onClick={() => onSave(localMapping)}
        >
          Save
        </button>
      </div>
    </div>
  );
}
