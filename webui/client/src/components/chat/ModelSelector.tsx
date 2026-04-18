import * as Popover from '@radix-ui/react-popover';
import { Loader2 } from 'lucide-react';
import { formatModelLabel } from '../../lib/formatModelLabel';

/**
 * Iterate 14.8.3 — ModelSelector redesign.
 *
 * Replaced the previous dual-state (userOverride + displayedId) design with
 * a purely props-driven component. The selector no longer touches
 * localStorage or tracks its own display state. Instead:
 *
 *   1. `systemInitModel` (from chatStore via ChatToolbar) seeds the active
 *      label. When the CLI reports a model, the display updates.
 *   2. `onSwitchModel` fires the /mode endpoint which respawns Claude with
 *      the chosen model. The display does NOT change on click — it updates
 *      when the new system/init event arrives via SSE and hydrates chatStore,
 *      which flows back as a new `systemInitModel` prop.
 *
 * This eliminates the taskKey-reset useEffect, the userOverride flag, and
 * the displayedId sync dance — all sources of stale-label bugs.
 */

export interface ConcreteModel {
  /** Full concrete id as it would appear in CLI system/init. */
  id: string;
  /** Coarse family alias understood by Claude CLI's --model flag. */
  alias: ModelOption;
  /** Optional context label shown next to the name (e.g. "1M", "200K"). */
  context?: string;
}

export type ModelOption = 'opus' | 'sonnet' | 'haiku';

// Iterate 14.7.1 — CLI-supported concrete models. Order matters:
// newest/flagship first within each family.
// Iterate 14.10 — Opus 4.7 is the correct CLI id for the newest flagship
// (verified via `claude --model claude-opus-4-7 -p "."` returning the same
// id in system/init). 14.9 guessed `claude-opus-7-0`, which is not a
// real CLI-recognised identifier.
export const KNOWN_MODELS: ConcreteModel[] = [
  { id: 'claude-opus-4-7', alias: 'opus', context: '1M' },
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
 *  need to forward an alias after the user picked a concrete option. Falls
 *  back to 'sonnet' for unknown ids (safest middle). */
export function aliasFromConcrete(id: string): ModelOption {
  const lower = id.toLowerCase();
  if (lower.includes('opus')) return 'opus';
  if (lower.includes('haiku')) return 'haiku';
  if (lower.includes('sonnet')) return 'sonnet';
  return 'sonnet';
}

interface ModelSelectorProps {
  /** Raw model id from chatStore.systemInit for the active task. */
  systemInitModel?: string;
  /** Callback fired when user selects a different model. Triggers mode
   *  switch via /mode endpoint. */
  onSwitchModel: (modelId: string) => void;
  /**
   * Iterate 14.13 — true while {@link useSwitchModel} mutation is in flight.
   * Legacy "Switching…" visual. Superseded (but still respected) by
   * {@link pendingTargetModel} which carries the user's chosen target id.
   */
  isSwitching?: boolean;
  /**
   * Iterate 2026-04-18 modelswitch-spawn-ux — the model id the user just
   * picked. While set, the trigger renders the TARGET label + a spinner
   * (not the stale `systemInitModel` label) so the user has continuous
   * visual feedback across the full 1-2s respawn. Cleared by the
   * caller (ChatToolbar) once `systemInitModel` matches the target or
   * on mutation error / timeout. Takes precedence over `isSwitching`
   * for labelling.
   */
  pendingTargetModel?: string;
}

export function ModelSelector({
  systemInitModel,
  onSwitchModel,
  isSwitching = false,
  pendingTargetModel,
}: ModelSelectorProps) {
  const matchedInit = matchKnownModel(systemInitModel);
  const showOther = !!systemInitModel && !matchedInit;
  const otherEntry: ConcreteModel | null = showOther
    ? { id: systemInitModel!, alias: aliasFromConcrete(systemInitModel!) }
    : null;

  const activeId = matchedInit?.id ?? otherEntry?.id ?? KNOWN_MODELS[0].id;
  const formattedLabel = formatModelLabel(activeId);
  const activeLabel = otherEntry && activeId === otherEntry.id
    ? `Other: ${activeId}`
    : formattedLabel;

  // Iterate 2026-04-18 — pending-target visual. When set, render the
  // TARGET label + spinner; falls back to "Switching…" + spinner if only
  // the legacy isSwitching is truthy. Disabled in both states.
  const matchedPending = matchKnownModel(pendingTargetModel);
  const pendingRawLabel = matchedPending
    ? formatModelLabel(matchedPending.id)
    : pendingTargetModel ?? '';
  const pendingLabel = matchedPending
    ? pendingRawLabel
    : pendingTargetModel
      ? pendingTargetModel // unknown id shown verbatim
      : '';

  const showPendingTarget = !!pendingTargetModel;
  const showSwitchingOnly = !showPendingTarget && isSwitching;
  const disabled = showPendingTarget || isSwitching;

  function handlePick(entry: ConcreteModel) {
    onSwitchModel(entry.id);
  }

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className="px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
          data-testid="model-selector-trigger"
          data-pending-target={pendingTargetModel ?? undefined}
          title={
            showPendingTarget
              ? `Switching to ${pendingTargetModel}…`
              : systemInitModel
                ? `Running: ${systemInitModel}`
                : 'Claude CLI model'
          }
          disabled={disabled}
        >
          {showPendingTarget ? (
            <>
              <Loader2 size={12} className="animate-spin" data-testid="model-switching-spinner" />
              <span>{pendingLabel}</span>
            </>
          ) : showSwitchingOnly ? (
            <>
              <Loader2 size={12} className="animate-spin" data-testid="model-switching-spinner" />
              <span>Switching…</span>
            </>
          ) : (
            activeLabel
          )}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-white rounded-lg shadow-lg border border-gray-200 py-1 min-w-[220px] z-50"
          sideOffset={4}
        >
          {KNOWN_MODELS.map((entry) => {
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
