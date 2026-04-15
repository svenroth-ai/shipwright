import { useEffect, useState } from 'react';
import * as Popover from '@radix-ui/react-popover';
import type { ModelOption } from '../../hooks/useChatSettings';
import { formatModelLabel } from '../../lib/formatModelLabel';

/**
 * Iterate 14.7.1 — extended model selector.
 *
 * Background: earlier iterates shipped a coarse `opus|sonnet|haiku` selector
 * (the three aliases the Claude CLI accepts on `--model`). Iterate 14.6 then
 * added a separate dynamic label next to the dropdown that echoed the CLI's
 * real `system/init.model` (e.g. `claude-opus-4-5-20251101`). Having both a
 * dropdown AND a dynamic label was redundant and confusing.
 *
 * This iterate collapses the two controls into one: the dropdown now lists
 * concrete CLI model ids (opus-4-5, opus-4-6, sonnet-4-5, sonnet-4-6,
 * haiku-4-5), displayed via formatModelLabel (e.g. "Opus 4.6"). The selected
 * concrete id auto-syncs to the system/init model on first event, unless
 * the user has manually picked an option in this task's session. An unknown
 * model from system/init is appended as "Other: {raw}" so we never crash on
 * a new CLI build.
 *
 * Wire compatibility: the CLI only accepts coarse aliases on --model. We map
 * the concrete id back to its family alias via `aliasFromConcrete()` before
 * calling `onChange`, so the server contract stays unchanged.
 */

export interface ConcreteModel {
  /** Full concrete id as it would appear in CLI system/init. */
  id: string;
  /** Coarse family alias understood by Claude CLI's --model flag. */
  alias: ModelOption;
  /** Optional context label shown next to the name (e.g. "1M", "200K"). */
  context?: string;
}

// Iterate 14.7.1 — the five CLI-supported concrete models. Order matters:
// newest/flagship first within each family.
export const KNOWN_MODELS: ConcreteModel[] = [
  { id: 'claude-opus-4-6', alias: 'opus', context: '1M' },
  { id: 'claude-opus-4-5', alias: 'opus', context: '200K' },
  { id: 'claude-sonnet-4-6', alias: 'sonnet', context: '1M' },
  { id: 'claude-sonnet-4-5', alias: 'sonnet', context: '200K' },
  { id: 'claude-haiku-4-5', alias: 'haiku', context: '200K' },
];

/** Parse an arbitrary CLI model id (possibly suffixed by a date like
 *  `-20251101`) and find the matching KNOWN_MODELS entry. Returns null for
 *  unknown ids so the caller can render "Other: {id}". */
export function matchKnownModel(rawId: string | undefined | null): ConcreteModel | null {
  if (!rawId) return null;
  const normalized = rawId.toLowerCase();
  // Direct match first
  const exact = KNOWN_MODELS.find((m) => normalized === m.id);
  if (exact) return exact;
  // Prefix match to absorb CLI date suffixes like `claude-opus-4-5-20251101`
  const prefix = KNOWN_MODELS.find((m) => normalized.startsWith(m.id + '-'));
  return prefix ?? null;
}

/** Coarse alias inferred from a concrete id by family name, used when we
 *  need to forward an `onChange(ModelOption)` after the user picked a
 *  concrete option. Falls back to 'sonnet' for unknown ids (safest middle). */
export function aliasFromConcrete(id: string): ModelOption {
  const lower = id.toLowerCase();
  if (lower.includes('opus')) return 'opus';
  if (lower.includes('haiku')) return 'haiku';
  if (lower.includes('sonnet')) return 'sonnet';
  return 'sonnet';
}

interface ModelSelectorProps {
  /** User-preference alias from localStorage (coarse family). */
  model: ModelOption;
  onChange: (model: ModelOption) => void;
  /**
   * Concrete CLI model id reported by the active task's `system/init` event.
   * When set and the user hasn't manually picked in this session, the
   * dropdown display flips to this id.
   */
  systemInitModel?: string;
  /**
   * Stable key identifying the active task. When it changes (task switch)
   * the "user manually changed" override is reset so the next task can
   * auto-sync again.
   */
  taskKey?: string;
}

export function ModelSelector({ model, onChange, systemInitModel, taskKey }: ModelSelectorProps) {
  // Track whether the user has manually picked in this session. Once true,
  // we stop following systemInitModel — the explicit click wins.
  const [userOverride, setUserOverride] = useState(false);
  const [displayedId, setDisplayedId] = useState<string | null>(null);

  // Reset override + display on task switch. Iterate 14.7.1 requirement: a
  // new task starts fresh; the next system/init will seed the label again.
  useEffect(() => {
    setUserOverride(false);
    setDisplayedId(null);
  }, [taskKey]);

  // Auto-sync from systemInitModel until user overrides.
  useEffect(() => {
    if (userOverride) return;
    if (!systemInitModel) return;
    setDisplayedId(systemInitModel);
  }, [systemInitModel, userOverride]);

  // Build the option list: the five known concrete models, plus an
  // "Other: {raw}" fallback entry when systemInit reported an unknown id.
  const knownList: ConcreteModel[] = KNOWN_MODELS;
  const matchedInit = matchKnownModel(systemInitModel);
  const showOther = !!systemInitModel && !matchedInit;
  const otherEntry: ConcreteModel | null = showOther
    ? { id: systemInitModel!, alias: aliasFromConcrete(systemInitModel!) }
    : null;

  // Decide which id is currently "active" for display purposes:
  // 1) The user's latest pick (displayedId set by onClick), OR
  // 2) The synced systemInit id (matched or raw other), OR
  // 3) The first known model whose alias matches the stored `model` prop.
  let activeId: string;
  if (displayedId) {
    activeId = displayedId;
  } else if (matchedInit) {
    activeId = matchedInit.id;
  } else if (otherEntry) {
    activeId = otherEntry.id;
  } else {
    activeId = knownList.find((m) => m.alias === model)?.id ?? knownList[0].id;
  }

  const activeLabel = matchKnownModel(activeId)
    ? formatModelLabel(activeId)
    : `Other: ${activeId}`;

  function handlePick(entry: ConcreteModel) {
    setUserOverride(true);
    setDisplayedId(entry.id);
    onChange(entry.alias);
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className="px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer"
          data-testid="model-selector-trigger"
          title={systemInitModel ? `CLI reports: ${systemInitModel}` : 'Claude CLI model'}
        >
          {activeLabel}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[220px] z-50"
          sideOffset={4}
        >
          {knownList.map((entry) => {
            const isActive = entry.id === activeId;
            return (
              <Popover.Close asChild key={entry.id}>
                <button
                  className={`flex items-center justify-between w-full px-3 py-1.5 text-left hover:bg-gray-50 ${isActive ? 'bg-gray-50' : ''}`}
                  onClick={() => handlePick(entry)}
                >
                  <span className="text-xs font-medium">{formatModelLabel(entry.id)}</span>
                  {entry.context && (
                    <span className="text-[10px] text-gray-400">{entry.context} ctx</span>
                  )}
                </button>
              </Popover.Close>
            );
          })}
          {otherEntry && (
            <Popover.Close asChild>
              <button
                className={`flex items-center justify-between w-full px-3 py-1.5 text-left hover:bg-gray-50 border-t border-gray-100 ${otherEntry.id === activeId ? 'bg-gray-50' : ''}`}
                onClick={() => handlePick(otherEntry)}
              >
                <span className="text-xs font-medium">Other: {otherEntry.id}</span>
              </button>
            </Popover.Close>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
