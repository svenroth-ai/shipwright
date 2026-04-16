import * as Popover from '@radix-ui/react-popover';
import { Hand, Code2, ClipboardList, Link2, Check, Loader2, Sparkles } from 'lucide-react';
import { useState, type ComponentType } from 'react';
import type { ModeOption } from '../../hooks/useChatSettings';
import { useChangeMode } from '../../hooks/useChangeMode';
import { ApiError } from '../../lib/api';

interface ModeEntry {
  value: ModeOption;
  label: string;
  shortLabel: string;
  description: string;
  icon: ComponentType<{ size?: number; className?: string }>;
}

/**
 * Permission modes matching the Claude CLI / VS Code extension.
 * Iterate 14.9 — Auto mode added as the new default (Claude picks the
 * best permission mode per turn; mirrors the VS Code extension toggle).
 */
const MODES: ModeEntry[] = [
  {
    value: 'auto',
    label: 'Auto mode',
    shortLabel: 'Auto',
    description: 'Claude will automatically choose the best permission mode for each task',
    icon: Sparkles,
  },
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
  /** Iterate 10 — when both are set, PermissionMode fires the mid-task
   *  switch mutation and only updates `onChange` on success. */
  projectId?: string;
  taskId?: string;
}

export function PermissionMode({ mode, onChange, projectId, taskId }: PermissionModeProps) {
  // Fallback to the first entry (Auto, iterate 14.9) if the mode value
  // isn't recognised — previous default was bypassPermissions.
  const current = MODES.find((m) => m.value === mode) ?? MODES[0];
  const Icon = current.icon;
  const [switchError, setSwitchError] = useState<string | null>(null);

  // Mid-task switch mutation — only active when we have both ids. Always
  // call the hook (rules of hooks), but no-op it when the ids are missing
  // by short-circuiting handleSelect to just call onChange.
  const changeMode = useChangeMode(projectId ?? '', taskId ?? '');
  const canSwitchLive = Boolean(projectId && taskId);

  function handleSelect(newMode: ModeOption) {
    setSwitchError(null);
    if (!canSwitchLive || newMode === mode) {
      onChange(newMode);
      return;
    }
    changeMode.mutate(newMode, {
      onSuccess: () => {
        onChange(newMode);
      },
      onError: (err) => {
        if (err instanceof ApiError) {
          setSwitchError(err.message);
        } else {
          setSwitchError(err instanceof Error ? err.message : 'Mode switch failed');
        }
      },
    });
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[var(--color-border,#e0dbd4)] text-xs font-medium text-gray-700 bg-white hover:border-[var(--color-primary,#6b5e56)] hover:text-gray-900 transition-colors cursor-pointer disabled:opacity-60"
          title={switchError ?? current.description}
          disabled={changeMode.isPending}
        >
          {changeMode.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Icon size={12} />
          )}
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
          {switchError && (
            <div className="px-3 py-2 text-[11px] text-red-600 border-b border-[var(--color-border,#e0dbd4)]">
              {switchError}
            </div>
          )}
          {MODES.map((m) => {
            const MIcon = m.icon;
            const isActive = m.value === mode;
            return (
              <Popover.Close asChild key={m.value}>
                <button
                  onClick={() => handleSelect(m.value)}
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
              </Popover.Close>
            );
          })}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
