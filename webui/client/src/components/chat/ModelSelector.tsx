import * as Popover from '@radix-ui/react-popover';
import type { ModelOption } from '../../hooks/useChatSettings';

const MODELS: { value: ModelOption; label: string; desc: string }[] = [
  { value: 'opus', label: 'Opus', desc: 'Most capable' },
  { value: 'sonnet', label: 'Sonnet', desc: 'Balanced' },
  { value: 'haiku', label: 'Haiku', desc: 'Fast' },
];

interface ModelSelectorProps {
  model: ModelOption;
  onChange: (model: ModelOption) => void;
}

export function ModelSelector({ model, onChange }: ModelSelectorProps) {
  const current = MODELS.find((m) => m.value === model)!;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer">
          {current.label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[140px] z-50" sideOffset={4}>
          {MODELS.map((m) => (
            <button
              key={m.value}
              className={`flex flex-col w-full px-3 py-1.5 text-left hover:bg-gray-50 ${m.value === model ? 'bg-gray-50' : ''}`}
              onClick={() => onChange(m.value)}
            >
              <span className="text-xs font-medium">{m.label}</span>
              <span className="text-[10px] text-gray-400">{m.desc}</span>
            </button>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
