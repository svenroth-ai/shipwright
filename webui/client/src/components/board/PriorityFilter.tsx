import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';

const PRIORITIES = [
  { value: null, label: 'All', dotColor: '' },
  { value: 'P1', label: 'P1 Critical', dotColor: 'bg-red-500' },
  { value: 'P2', label: 'P2 High', dotColor: 'bg-amber-500' },
  { value: 'P3', label: 'P3 Normal', dotColor: 'bg-gray-400' },
];

interface PriorityFilterProps {
  selectedPriority: string | null;
  onSelect: (priority: string | null) => void;
}

export function PriorityFilter({ selectedPriority, onSelect }: PriorityFilterProps) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[13px] font-medium text-gray-500 bg-[var(--color-muted-bg,#ede8e1)] hover:bg-gray-200 transition-colors">
          {selectedPriority ?? 'Priority'}
          <ChevronDown size={12} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-white rounded-lg shadow-lg border border-gray-200 p-2 min-w-[150px] z-50"
          sideOffset={4}
        >
          {PRIORITIES.map((p) => (
            <button
              key={p.label}
              className={`flex items-center gap-2 w-full px-2 py-1.5 rounded text-sm text-left hover:bg-gray-50 ${
                selectedPriority === p.value ? 'bg-gray-50 font-medium' : ''
              }`}
              onClick={() => onSelect(p.value)}
            >
              {p.dotColor && <span className={`w-2.5 h-2.5 rounded-full ${p.dotColor}`} />}
              {p.label}
            </button>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
