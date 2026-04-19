/*
 * Inbox derivation — surfaces pending interactions from the session JSONL.
 *
 * Input:  parsed events (from session-parser) + the set of tool names we
 *         consider "user-blocking" (allowlist).
 * Output: tool_use ids whose matching tool_result has NOT yet appeared,
 *         filtered by the allowlist. These are surfaced to the user as
 *         inbox entries ("Waiting for you to answer in your chat client").
 *
 * Rationale for allowlist (GPT MAJOR 8): plain long-running tools like
 * `Bash` open-ended commands aren't user-blocking — they finish on their
 * own. Only a narrow set is: AskUserQuestion + plugin-registered ones.
 *
 * Labelled "best-effort" in the UI per round-3 integration: tool_use
 * without matching tool_result is a heuristic, not a semantic contract.
 *
 * Persisted state lives in the SdkSessionsStore per task:
 *   - `pendingToolUseIds` — currently unresolved ids
 *   - `dismissedToolUseIds` — user clicked "Dismiss" on a false positive
 *   - `lastProcessedByteOffset` — incremental marker (unused in v1
 *      because deriveInbox reparses from top; kept as the field the
 *      Sub-iterate 1 fastpath will use)
 */

import type { ParsedSessionEvent } from "./session-parser.js";
import { extractToolResults, extractToolUses } from "./session-parser.js";

export const DEFAULT_USER_BLOCKING_TOOLS = new Set<string>(["AskUserQuestion"]);

export interface DeriveInboxArgs {
  events: ParsedSessionEvent[];
  allowlist?: Set<string>;
  /** Ids the user explicitly dismissed; never resurface. */
  dismissed?: Set<string>;
}

export interface InboxEntry {
  toolUseId: string;
  toolName: string;
  input: unknown;
  /** Assistant event index in `events`. */
  atAssistantEvent: number;
}

export interface DeriveInboxResult {
  pending: InboxEntry[];
  /** All tool_use ids (blocking + non-blocking) seen; diagnostics only. */
  allToolUseIds: string[];
  /** Resolved ids (had matching tool_result). Useful to shrink the store. */
  resolvedToolUseIds: string[];
}

export function deriveInbox(args: DeriveInboxArgs): DeriveInboxResult {
  const allowlist = args.allowlist ?? DEFAULT_USER_BLOCKING_TOOLS;
  const dismissed = args.dismissed ?? new Set<string>();
  const uses = extractToolUses(args.events);
  const results = extractToolResults(args.events);
  const resolvedIds = new Set(results.map((r) => r.toolUseId));

  const pending: InboxEntry[] = [];
  for (const u of uses) {
    if (resolvedIds.has(u.id)) continue;
    if (dismissed.has(u.id)) continue;
    if (!allowlist.has(u.name)) continue;
    pending.push({
      toolUseId: u.id,
      toolName: u.name,
      input: u.input,
      atAssistantEvent: u.atAssistantEvent,
    });
  }

  return {
    pending,
    allToolUseIds: uses.map((u) => u.id),
    resolvedToolUseIds: Array.from(resolvedIds),
  };
}
