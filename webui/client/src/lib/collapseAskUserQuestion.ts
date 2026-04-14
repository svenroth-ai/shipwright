import type { ChatMessage } from '../types';

/**
 * Claude Code CLI in `-p` + stream-json mode does NOT block generation on
 * `tool_use AskUserQuestion`. It emits the tool call and keeps generating
 * more content in the same assistant turn — often a markdown "Let me know…"
 * fallback list that mirrors the tool_use questions.
 *
 * This pure helper collapses that noise for display:
 *
 * - The FIRST `tool_use AskUserQuestion` is kept as-is.
 * - A **suppression window** opens immediately after it and closes at the
 *   next non-text message (tool_use, thinking, user, tool_result that does
 *   NOT belong to the opening AskUserQuestion, or end of array).
 * - Inside the window we drop any `assistant` / `result` text (markdown
 *   fallback) AND any subsequent `tool_use AskUserQuestion` (Claude's
 *   iterate-9 duplicate emission).
 * - Resolution of the opening AskUserQuestion (matching `tool_result` or
 *   pre-folded `toolOutput`) does NOT re-open the markdown — once dropped,
 *   always dropped. This is the iterate 13.1 fix: previously the window
 *   closed on resolution and the suppressed markdown became visible again
 *   as soon as the user answered.
 *
 * Runs AFTER `foldToolResults`.
 */
export function collapseAskUserQuestionRun(messages: ChatMessage[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  let pendingAskId: string | null = null;

  for (const m of messages) {
    if (pendingAskId !== null) {
      // The standalone tool_result that resolves the opening AskUserQuestion
      // renders normally and closes the suppression window.
      if (m.type === 'tool_result' && m.toolUseId === pendingAskId) {
        pendingAskId = null;
        result.push(m);
        continue;
      }
      // Suppress follow-up AskUserQuestion cards (iterate-9 duplicates).
      if (m.type === 'tool_use' && m.toolName === 'AskUserQuestion') {
        continue;
      }
      // Suppress assistant / result markdown fallback text blocks.
      if (m.type === 'assistant' || m.type === 'result') {
        continue;
      }
      // Any other message type (thinking, user, system, other tool_use like
      // TodoWrite/Bash/Edit, unrelated tool_result) ends the suppression
      // window — that content is real "next action" and should render.
      pendingAskId = null;
      result.push(m);
      continue;
    }

    // Not currently in a suppression window. Does this message OPEN one?
    if (
      m.type === 'tool_use' &&
      m.toolName === 'AskUserQuestion' &&
      m.toolUseId
    ) {
      // Open the window whether or not the tool_use is already folded.
      // A folded AskUserQuestion still has the markdown fallback immediately
      // after it in the persisted history, and we want to hide that
      // permanently.
      pendingAskId = m.toolUseId;
      result.push(m);
      continue;
    }

    result.push(m);
  }

  return result;
}
