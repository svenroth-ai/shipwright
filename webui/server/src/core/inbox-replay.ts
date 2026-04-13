import type { ChatMessage } from "../../../client/src/types/chat.js";
import { extractAskUserPayload } from "../../../client/src/lib/askUserPayload.js";

/**
 * A single reconstructable inbox item extracted from chat history.
 * Used by `inbox-replay` to rehydrate pending AskUserQuestions after a
 * server restart — see iterate-2026-04-13-wiring-fixes spec for why.
 */
export interface OrphanAskUserQuestion {
  taskId: string;
  toolUseId: string;
  question: string;
  context?: string;
  options?: string[];
  createdAt: string;
}

/**
 * Find `tool_use AskUserQuestion` entries in a chat-history message list that
 * DON'T yet have a matching `tool_result` by `toolUseId`. These are the
 * "still pending" questions we want to reconstruct in the inbox after a
 * restart so the user doesn't lose them.
 *
 * Pure function: input is a loaded message list, output is the orphan list
 * in chronological order (earliest first). Messages without a toolUseId are
 * skipped — they can't be correlated reliably.
 */
export function findOrphanAskUserQuestions(
  messages: ChatMessage[],
): OrphanAskUserQuestion[] {
  // Collect the set of toolUseIds that have a tool_result. These are
  // "resolved" and should NOT be reconstructed.
  const resolved = new Set<string>();
  for (const m of messages) {
    if (m.type === "tool_result" && m.toolUseId) {
      resolved.add(m.toolUseId);
    }
  }

  const orphans: OrphanAskUserQuestion[] = [];
  for (const m of messages) {
    if (
      m.type === "tool_use" &&
      m.toolName === "AskUserQuestion" &&
      m.toolUseId &&
      !resolved.has(m.toolUseId)
    ) {
      const payload = extractAskUserPayload(m.toolInput);
      orphans.push({
        taskId: m.taskId,
        toolUseId: m.toolUseId,
        question: payload.question || "Question from Claude",
        context: payload.context,
        options: payload.options,
        createdAt: m.timestamp,
      });
    }
  }
  return orphans;
}
