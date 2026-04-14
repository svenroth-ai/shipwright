import { useLocalStorage } from './useLocalStorage';

export type ModelOption = 'opus' | 'sonnet' | 'haiku';

/**
 * Claude CLI permission modes (matches --permission-mode flag values).
 * Default in our UI is `bypassPermissions` — the same mode VS Code's
 * Claude extension ships with. Users who want stricter approval can
 * switch via the pill in the chat toolbar.
 */
export type ModeOption = 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions';

export interface ChatSettings {
  model: ModelOption;
  mode: ModeOption;
}

/**
 * Migrate legacy localStorage values that used the old mode names
 * (default/plan/auto-accept) to the new CLI-aligned names.
 */
function migrateMode(raw: unknown): ModeOption {
  if (raw === 'default' || raw === 'acceptEdits' || raw === 'plan' || raw === 'bypassPermissions') {
    return raw;
  }
  if (raw === 'auto-accept') return 'acceptEdits';
  return 'bypassPermissions';
}

export function useChatSettings() {
  const [model, setModel] = useLocalStorage<ModelOption>('chat-model', 'sonnet');
  const [rawMode, setRawMode] = useLocalStorage<ModeOption>('chat-mode', 'bypassPermissions');

  const mode = migrateMode(rawMode);

  return { model, setModel, mode, setMode: setRawMode };
}
