import type { EffortOption } from '../../hooks/useChatSettings';

const CYCLE: EffortOption[] = ['low', 'medium', 'high', 'max'];
const LABELS: Record<EffortOption, string> = {
  low: 'Low',
  medium: 'Med',
  high: 'High',
  max: 'Max',
};
const TITLES: Record<EffortOption, string> = {
  low: 'Low — default thinking',
  medium: 'Medium — /think',
  high: 'High — /think hard',
  max: 'Max — /ultrathink',
};

interface EffortPillProps {
  effort: EffortOption;
  onChange: (effort: EffortOption) => void;
}

export function EffortPill({ effort, onChange }: EffortPillProps) {
  function handleClick() {
    const idx = CYCLE.indexOf(effort);
    onChange(CYCLE[(idx + 1) % CYCLE.length]);
  }

  return (
    <button
      className="px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer"
      onClick={handleClick}
      title={TITLES[effort]}
    >
      {LABELS[effort]}
    </button>
  );
}
