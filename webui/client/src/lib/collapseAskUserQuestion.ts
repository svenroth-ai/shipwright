import type { ChatMessage } from '../types';

/**
 * Claude Code CLI in `-p` + stream-json mode does NOT block generation on
 * `tool_use AskUserQuestion`. It emits the tool call and keeps generating
 * more content in the same assistant turn — often a slightly-different
 * second AskUserQuestion and a markdown "Let me know…" fallback list.
 * See iterate-2026-04-13-wiring-fixes spec (section 2) for the full story.
 *
 * This pure helper collapses that noise for display:
 *
 * - The FIRST `tool_use AskUserQuestion` is kept as-is.
 * - Until that card is resolved (matching `tool_result`, or the `tool_use`
 *   already has `toolOutput` set from foldToolResults), we suppress:
 *     - any subsequent `tool_use AskUserQuestion` (noise duplicate cards)
 *     - any `assistant` or `result` text blocks (markdown fallback content)
 * - Other message types (Bash/Edit tool_use, thinking, user, system) pass
 *   through untouched even while a question is pending.
 * - Once resolved, everything after the resolution renders normally.
 *
 * Runs AFTER `foldToolResults` — a folded tool_use that already has its
 * `toolOutput` is treated as resolved immediately and does NOT open a
 * pending run.
 */
export function collapseAskUserQuestionRun(messages: ChatMessage[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  let pendingAskId: string | null = null;

  for (const m of messages) {
    if (pendingAskId !== null) {
      // Resolution via standalone tool_result
      if (m.type === 'tool_result' && m.toolUseId === pendingAskId) {
        pendingAskId = null;
        result.push(m);
        continue;
      }
      // Suppress follow-up AskUserQuestion cards (the iterate-9 duplicates)
      if (m.type === 'tool_use' && m.toolName === 'AskUserQuestion') {
        continue;
      }
      // Suppress assistant / result text blocks (markdown fallback content)
      if (m.type === 'assistant' || m.type === 'result') {
        continue;
      }
      // Other types (Bash/Edit/thinking/user/system) pass through
      result.push(m);
      continue;
    }

    // Not currently pending. Does this message OPEN a new pending run?
    if (
      m.type === 'tool_use' &&
      m.toolName === 'AskUserQuestion' &&
      m.toolUseId
    ) {
      // Already folded (has a toolOutput from foldToolResults)? Treat as
      // resolved — render it but don't open a pending suppression window.
      if (m.toolOutput !== undefined) {
        result.push(m);
        continue;
      }
      pendingAskId = m.toolUseId;
      result.push(m);
      continue;
    }

    result.push(m);
  }

  return result;
}
