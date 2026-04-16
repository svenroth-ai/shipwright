import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocalStorage } from './useLocalStorage';
import { apiFetch } from '../lib/api';
import type { GlobalSettings } from '../types';

export type ModelOption = 'opus' | 'sonnet' | 'haiku';

/**
 * Claude CLI permission modes (matches --permission-mode flag values).
 *
 * Iterate 14.9 — `auto` added. In Auto mode the CLI picks the best
 * permission mode per turn (mirrors the VS Code extension's Auto mode
 * toggle). This is now the default for new chat sessions.
 */
export type ModeOption = 'auto' | 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions';

const VALID_MODES: readonly ModeOption[] = [
  'auto',
  'default',
  'acceptEdits',
  'plan',
  'bypassPermissions',
];

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

/**
 * Iterate 14.12 (Bug 2) — first-run hydration of `chat-mode` from
 * server settings. If a fresh browser has no `chat-mode` key in
 * localStorage AND the server settings define a `defaultMode`, we
 * mirror that into localStorage so NewIssueModal's task creation picks
 * up the user's chosen default instead of falling back to the hardcoded
 * `'auto'` from useLocalStorage.
 *
 * After this hydration, subsequent in-chat mode toggles via the
 * PermissionMode dropdown override the value as before — and saving
 * Settings → Default Mode keeps both in sync via SettingsPage's
 * `saveDefaultMode` helper.
 */
export function useChatSettings() {
  const [model, setModel] = useLocalStorage<ModelOption>('chat-model', 'sonnet');
  const [rawMode, setRawMode] = useLocalStorage<ModeOption>('chat-mode', 'auto');

  // Note: separate cached settings query (sharing the key with
  // useSettings()) so we don't pull in its full hook surface here.
  // React Query dedupes by queryKey, so this is one network call total.
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiFetch<GlobalSettings>('/settings'),
    staleTime: 30_000,
  });

  useEffect(() => {
    // Hydrate ONLY when the localStorage key was never set (raw read,
    // not the migrated value). useLocalStorage stores `defaultValue`
    // in state but does NOT write it to localStorage, so a missing key
    // is detectable via direct read.
    let stored: string | null = null;
    try {
      stored = localStorage.getItem('chat-mode');
    } catch {
      // SSR / privacy mode — nothing to hydrate.
      return;
    }
    if (stored !== null) return;
    const serverDefault = settings?.defaultMode;
    if (
      typeof serverDefault === 'string' &&
      (VALID_MODES as readonly string[]).includes(serverDefault)
    ) {
      setRawMode(serverDefault as ModeOption);
    }
  }, [settings?.defaultMode, setRawMode]);

  const mode = migrateMode(rawMode);

  return { model, setModel, mode, setMode: setRawMode };
}
