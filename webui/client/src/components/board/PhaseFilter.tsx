import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';
import { PIPELINE_PHASES } from '../../lib/phaseMapping';

const PHASE_DOT_COLORS: Record<string, string> = {
  project: 'bg-gray-400',
  design: 'bg-purple-500',
  plan: 'bg-blue-500',
  build: 'bg-orange-500',
  test: 'bg-green-500',
  security: 'bg-red-500',
  compliance: 'bg-indigo-500',
  changelog: 'bg-yellow-500',
  deploy: 'bg-teal-500',
};

const PHASES = PIPELINE_PHASES.map((name) => ({
  name,
  color: PHASE_DOT_COLORS[name] ?? 'bg-gray-400',
}));

interface PhaseFilterProps {
  selectedPhases: string[];
  onToggle: (phase: string) => void;
  onClear: () => void;
}

export function PhaseFilter({ selectedPhases, onToggle, onClear }: PhaseFilterProps) {
  const count = selectedPhases.length;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[13px] font-medium text-gray-500 bg-[var(--color-muted-bg,#ede8e1)] hover:bg-gray-200 transition-colors">
          Phase
          {count > 0 && (
            <span className="min-w-[18px] h-[18px] rounded-full bg-[var(--color-primary)] text-white text-[10px] font-bold flex items-center justify-center">
              {count}
            </span>
          )}
          <ChevronDown size={12} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-white rounded-lg shadow-lg border border-[#e0dbd4] p-2 min-w-[160px] z-50"
          sideOffset={4}
        >
          {PHASES.map((phase) => (
            <label
              key={phase.name}
              className="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-gray-50 text-sm"
            >
              <input
                type="checkbox"
                checked={selectedPhases.includes(phase.name)}
                onChange={() => onToggle(phase.name)}
                className="rounded border-gray-300"
              />
              <span className={`w-2.5 h-2.5 rounded-full ${phase.color}`} />
              <span className="capitalize">{phase.name}</span>
            </label>
          ))}
          {count > 0 && (
            <button
              className="w-full text-center text-xs text-[var(--color-primary)] mt-1 pt-1 border-t border-gray-100 hover:underline"
              onClick={onClear}
            >
              Clear all
            </button>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
