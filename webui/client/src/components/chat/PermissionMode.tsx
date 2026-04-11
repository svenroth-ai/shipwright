import * as Popover from '@radix-ui/react-popover';
import type { ModeOption } from '../../hooks/useChatSettings';

const MODES: { value: ModeOption; label: string; desc: string }[] = [
  { value: 'default', label: 'Default', desc: 'Approve each action' },
  { value: 'plan', label: 'Plan', desc: 'Planning only, no edits' },
  { value: 'auto-accept', label: 'Auto-accept', desc: 'Accept all actions' },
];

interface PermissionModeProps {
  mode: ModeOption;
  onChange: (mode: ModeOption) => void;
}

export function PermissionMode({ mode, onChange }: PermissionModeProps) {
  const current = MODES.find((m) => m.value === mode) ?? MODES[0];

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer">
          {current.label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[180px] z-50" sideOffset={4}>
          {MODES.map((m) => (
            <button
              key={m.value}
              className={`flex flex-col w-full px-3 py-1.5 text-left hover:bg-gray-50 ${m.value === mode ? 'bg-gray-50' : ''}`}
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
