import * as Popover from '@radix-ui/react-popover';
import type { ModelOption } from '../../hooks/useChatSettings';

const MODELS: { value: ModelOption; label: string; context: string }[] = [
  // Iterate 11 — Sonnet 4.6 supports 1M context (same as Opus 4.6).
  // Haiku 4.5 stays at 200K (standard Anthropic context window).
  { value: 'opus', label: 'Claude Opus 4.6', context: '1M' },
  { value: 'sonnet', label: 'Claude Sonnet 4.6', context: '1M' },
  { value: 'haiku', label: 'Claude Haiku 4.5', context: '200K' },
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
        <Popover.Content className="bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[200px] z-50" sideOffset={4}>
          {/* Iterate 11 — wrap in Popover.Close so selecting a model
              closes the popover (same pattern as PermissionMode). */}
          {MODELS.map((m) => (
            <Popover.Close asChild key={m.value}>
              <button
                className={`flex items-center justify-between w-full px-3 py-1.5 text-left hover:bg-gray-50 ${m.value === model ? 'bg-gray-50' : ''}`}
                onClick={() => onChange(m.value)}
              >
                <span className="text-xs font-medium">{m.label}</span>
                <span className="text-[10px] text-gray-400">{m.context} ctx</span>
              </button>
            </Popover.Close>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
