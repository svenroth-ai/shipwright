import * as Popover from '@radix-ui/react-popover';
import { Hand, Code2, ClipboardList, Link2, Check } from 'lucide-react';
import type { ComponentType } from 'react';
import type { ModeOption } from '../../hooks/useChatSettings';

interface ModeEntry {
  value: ModeOption;
  label: string;
  shortLabel: string;
  description: string;
  icon: ComponentType<{ size?: number; className?: string }>;
}

/**
 * Four permission modes matching VS Code's Claude extension.
 * `bypassPermissions` is the default — matches the VS Code default
 * and the user's expectation of "just run stuff".
 */
const MODES: ModeEntry[] = [
  {
    value: 'default',
    label: 'Ask before edits',
    shortLabel: 'Ask',
    description: 'Claude will ask for approval before making each edit',
    icon: Hand,
  },
  {
    value: 'acceptEdits',
    label: 'Edit automatically',
    shortLabel: 'Auto-edit',
    description: 'Claude will edit your selected text or the whole file',
    icon: Code2,
  },
  {
    value: 'plan',
    label: 'Plan mode',
    shortLabel: 'Plan',
    description: 'Claude will explore the code and present a plan before editing',
    icon: ClipboardList,
  },
  {
    value: 'bypassPermissions',
    label: 'Bypass permissions',
    shortLabel: 'Bypass',
    description: 'Claude will not ask for approval before running potentially dangerous commands',
    icon: Link2,
  },
];

interface PermissionModeProps {
  mode: ModeOption;
  onChange: (mode: ModeOption) => void;
}

export function PermissionMode({ mode, onChange }: PermissionModeProps) {
  const current = MODES.find((m) => m.value === mode) ?? MODES[3];
  const Icon = current.icon;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[var(--color-border,#e0dbd4)] text-xs font-medium text-gray-700 bg-white hover:border-[var(--color-primary,#6b5e56)] hover:text-gray-900 transition-colors cursor-pointer"
          title={current.description}
        >
          <Icon size={12} />
          {current.shortLabel}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-white rounded-xl shadow-[0_8px_24px_rgba(0,0,0,0.12)] border border-[var(--color-border,#e0dbd4)] py-1 min-w-[320px] z-50"
          sideOffset={6}
          align="start"
        >
          <div className="px-3 py-2 border-b border-[var(--color-border,#e0dbd4)] flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-900">Modes</span>
            <span className="text-[10px] text-gray-400">
              <kbd className="px-1 py-0.5 rounded bg-gray-100 border border-gray-200 font-mono">shift</kbd>
              {' + '}
              <kbd className="px-1 py-0.5 rounded bg-gray-100 border border-gray-200 font-mono">tab</kbd>
              {' to switch'}
            </span>
          </div>
          {MODES.map((m) => {
            const MIcon = m.icon;
            const isActive = m.value === mode;
            return (
              <button
                key={m.value}
                onClick={() => onChange(m.value)}
                className={`flex items-start gap-3 w-full px-3 py-2.5 text-left hover:bg-[var(--color-muted-bg,#ede8e1)] transition-colors ${
                  isActive ? 'bg-[var(--color-muted-bg,#ede8e1)]' : ''
                }`}
              >
                <div className="flex items-center justify-center w-7 h-7 rounded-md bg-gray-100 text-gray-600 shrink-0 mt-0.5">
                  <MIcon size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[13px] font-semibold text-gray-900 flex items-center gap-2">
                    {m.label}
                  </div>
                  <div className="text-[11px] text-gray-500 leading-snug mt-0.5">
                    {m.description}
                  </div>
                </div>
                {isActive && (
                  <Check size={14} className="text-[var(--color-primary,#6b5e56)] shrink-0 mt-1" />
                )}
              </button>
            );
          })}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
