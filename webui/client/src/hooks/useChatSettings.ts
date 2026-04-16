import { useLocalStorage } from './useLocalStorage';

export type ModelOption = 'opus' | 'sonnet' | 'haiku';

/**
 * Claude CLI permission modes (matches --permission-mode flag values).
 *
 * Iterate 14.9 — `auto` added. In Auto mode the CLI picks the best
 * permission mode per turn (mirrors the VS Code extension's Auto mode
 * toggle). This is now the default for new chat sessions.
 */
export type ModeOption = 'auto' | 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions';

export interface ChatSettings {
  model: ModelOption;
  mode: ModeOption;
}

/**
 * Migrate legacy localStorage values that used the old mode names
 * (default/plan/auto-accept) to the new CLI-aligned names.
 */
function migrateMode(raw: unknown): ModeOption {
  if (
    raw === 'auto' ||
    raw === 'default' ||
    raw === 'acceptEdits' ||
    raw === 'plan' ||
    raw === 'bypassPermissions'
  ) {
    return raw;
  }
  if (raw === 'auto-accept') return 'acceptEdits';
  return 'auto';
}

export function useChatSettings() {
  const [model, setModel] = useLocalStorage<ModelOption>('chat-model', 'sonnet');
  const [rawMode, setRawMode] = useLocalStorage<ModeOption>('chat-mode', 'auto');

  const mode = migrateMode(rawMode);

  return { model, setModel, mode, setMode: setRawMode };
}
