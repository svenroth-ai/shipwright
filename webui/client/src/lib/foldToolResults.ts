import type { ChatMessage } from '../types';

/**
 * Fold tool_result messages into their matching tool_use messages by toolUseId.
 *
 * The chat-history stream records tool_use and tool_result as separate entries
 * so persistence is append-only and lossless. For display, we want a single
 * "tool call" card that shows both the invocation and its result (or stays
 * "Running" while the result is still pending). This helper walks the message
 * list once and, whenever a tool_result's toolUseId matches an earlier
 * tool_use, copies the result content + error flag onto the tool_use message
 * and drops the standalone tool_result.
 *
 * Orphan tool_results (no matching tool_use in the list) and legacy messages
 * without a toolUseId are passed through unchanged so older chat histories
 * keep rendering.
 */
export function foldToolResults(messages: ChatMessage[]): ChatMessage[] {
  const toolUseIndex = new Map<string, number>();
  const result: ChatMessage[] = [];

  for (const m of messages) {
    if (m.type === 'tool_use' && m.toolUseId) {
      toolUseIndex.set(m.toolUseId, result.length);
      result.push(m);
      continue;
    }

    if (m.type === 'tool_result' && m.toolUseId) {
      const idx = toolUseIndex.get(m.toolUseId);
      if (idx != null) {
        const parent = result[idx];
        result[idx] = {
          ...parent,
          toolOutput: m.content,
          isError: m.isError === true ? true : parent.isError,
        };
        continue;
      }
    }

    result.push(m);
  }

  return result;
}
