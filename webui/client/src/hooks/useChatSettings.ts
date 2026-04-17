import { useEffect, useCallback, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocalStorage } from './useLocalStorage';
import { apiFetch } from '../lib/api';
import { KNOWN_MODELS } from '../components/chat/ModelSelector';
import type { GlobalSettings } from '../types';

/**
 * Sub-iterate C (assistant-ui-migration campaign, 2026-04-17).
 *
 * Model state unification: the `model` field is now a concrete CLI id
 * (`claude-opus-4-7`, `claude-sonnet-4-6`, ...) — NOT the coarse alias
 * union (`'opus' | 'sonnet' | 'haiku'`) that shipped through iterate
 * 14.12. The alias caused `useCreateTask` to send `body.model = 'opus'`,
 * which the Claude CLI resolves to its compiled-in default-stable (4.5
 * / 4.6 in CLI 2.1.1) — silently dropping the user's explicit pick.
 *
 * Migration strategy:
 *  1. Legacy localStorage values ('opus' / 'sonnet' / 'haiku') are
 *     silently upgraded on read to the first KNOWN_MODELS entry of the
 *     same family.
 *  2. Empty localStorage hydrates from `settings.defaultModel` on first
 *     mount — mirror of the 14.12 `mode` hydration flow.
 *  3. External writers (`ModelSelector` → `useSwitchModel`) keep
 *     `setModel` in sync via `ChatToolbar`, so a mid-task switch also
 *     updates the fallback for future new tasks.
 */

export type ModeOption = 'auto' | 'default' | 'acceptEdits' | 'plan' | 'bypassPermissions';

/**
 * @deprecated kept as an export only for backwards compatibility with
 * `ModelSelector.ConcreteModel.alias`. External consumers should not use
 * this type for localStorage or for task-creation payloads — use a
 * concrete CLI id string instead.
 */
export type ModelOption = 'opus' | 'sonnet' | 'haiku';

const VALID_MODES: readonly ModeOption[] = [
  'auto',
  'default',
  'acceptEdits',
  'plan',
  'bypassPermissions',
];

export interface ChatSettings {
  /** Concrete CLI model id (e.g. `claude-opus-4-7`). Never a coarse alias. */
  model: string;
  mode: ModeOption;
}

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
 * Migrate a legacy alias value to its newest concrete KNOWN_MODELS entry.
 * Returns null when the input is already a concrete id or doesn't match
 * a known alias.
 */
export function upgradeLegacyModelAlias(raw: string | null): string | null {
  if (!raw) return null;
  if (raw === 'opus' || raw === 'sonnet' || raw === 'haiku') {
    const match = KNOWN_MODELS.find((m) => m.alias === raw);
    return match?.id ?? null;
  }
  return null;
}

const MODEL_STORAGE_KEY = 'chat-model';
const FALLBACK_MODEL_ID = KNOWN_MODELS[0]?.id ?? 'claude-opus-4-7';

function readInitialModel(): { value: string; wasStored: boolean; wasLegacyAlias: boolean } {
  try {
    const raw = localStorage.getItem(MODEL_STORAGE_KEY);
    if (raw === null) {
      return { value: FALLBACK_MODEL_ID, wasStored: false, wasLegacyAlias: false };
    }
    // Stored values are JSON-encoded by useLocalStorage.
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed === 'string') {
      const upgraded = upgradeLegacyModelAlias(parsed);
      if (upgraded) {
        return { value: upgraded, wasStored: true, wasLegacyAlias: true };
      }
      return { value: parsed, wasStored: true, wasLegacyAlias: false };
    }
    return { value: FALLBACK_MODEL_ID, wasStored: false, wasLegacyAlias: false };
  } catch {
    return { value: FALLBACK_MODEL_ID, wasStored: false, wasLegacyAlias: false };
  }
}

function writeModel(value: string): void {
  try {
    localStorage.setItem(MODEL_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // SSR / privacy mode — non-fatal.
  }
}

export function useChatSettings() {
  const [initial] = useState(readInitialModel);
  const [model, setModelState] = useState<string>(initial.value);
  // Keep localStorage and React state in lockstep. Silent legacy-alias
  // upgrade happens on first read — persist immediately so the next
  // component mount sees the concrete id directly.
  const [modelHydrated, setModelHydrated] = useState<boolean>(
    initial.wasStored && !initial.wasLegacyAlias
  );

  useEffect(() => {
    if (initial.wasLegacyAlias) {
      writeModel(initial.value);
    }
  }, [initial.wasLegacyAlias, initial.value]);

  const setModel = useCallback((value: string) => {
    setModelState(value);
    writeModel(value);
    setModelHydrated(true);
  }, []);

  const [rawMode, setRawMode] = useLocalStorage<ModeOption>('chat-mode', 'auto');

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiFetch<GlobalSettings>('/settings'),
    staleTime: 30_000,
  });

  // Hydrate `model` from server `settings.defaultModel` ONLY when
  // localStorage was empty on first mount. Mid-session changes to
  // defaultModel do NOT overwrite the user's active model.
  useEffect(() => {
    if (modelHydrated) return;
    if (initial.wasStored) {
      setModelHydrated(true);
      return;
    }
    const serverDefault = settings?.defaultModel;
    if (typeof serverDefault === 'string' && serverDefault.length > 0) {
      setModelState(serverDefault);
      writeModel(serverDefault);
      setModelHydrated(true);
    }
  }, [settings?.defaultModel, modelHydrated, initial.wasStored]);

  // Hydrate `mode` from server settings on first mount (iterate 14.12).
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem('chat-mode');
    } catch {
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
