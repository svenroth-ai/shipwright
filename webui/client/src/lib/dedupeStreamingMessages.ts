import type { ChatMessage } from '../types';

/**
 * Remove streaming ChatMessages that are already present in the persisted
 * list, to avoid rendering the same event twice.
 *
 * Why this exists: the server persists every NDJSON chat event to
 * chat-store AND broadcasts it via SSE. The client then ends up with the
 * same event in two places:
 *   1. `messages` (persisted) — refetched when useSSE invalidates the
 *      chat query on each `chat:message` event.
 *   2. `streaming.streamingMessages` (live) — populated by
 *      useStreamingChat.processNdjsonMessage from the same SSE event.
 * ChatPanel renders both arrays sequentially, so without dedupe the user
 * sees two cards for a single tool call or AskUserQuestion prompt.
 *
 * Stable signature:
 *   - tool_use / tool_result with a toolUseId → `tool:<toolUseId>`
 *     (unique per tool invocation, thanks to iterate-2's toolUseId
 *      propagation through the NDJSON parser and streaming hook).
 *   - everything else → `<type>:<content-prefix-200>`
 *     (assistant text, thinking, system messages, legacy tool_use
 *      without a toolUseId).
 * The signature intentionally ignores the generated `id` field because
 * the server parser and the client streaming hook each generate their
 * own, so IDs never match between the two flows.
 */
function signatureOf(msg: ChatMessage): string {
  if (msg.toolUseId) return `tool:${msg.toolUseId}`;
  return `${msg.type}:${msg.content.slice(0, 200)}`;
}

export function dedupeStreamingMessages(
  persisted: ChatMessage[],
  streaming: ChatMessage[],
): ChatMessage[] {
  if (persisted.length === 0) return streaming;
  const seen = new Set<string>();
  for (const m of persisted) {
    seen.add(signatureOf(m));
  }
  return streaming.filter((m) => !seen.has(signatureOf(m)));
}
