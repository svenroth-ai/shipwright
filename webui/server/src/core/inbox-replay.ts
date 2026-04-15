import type { ChatMessage } from "../../../client/src/types/chat.js";
import type { InboxItemPart } from "../../../client/src/types/inbox.js";
import { extractAskUserPayload } from "../../../client/src/lib/askUserPayload.js";

/**
 * A single reconstructable inbox item extracted from chat history.
 * Used by `inbox-replay` to rehydrate pending AskUserQuestions after a
 * server restart — see iterate-2026-04-13-wiring-fixes spec for why.
 *
 * Iterate 14.2: switched from single question/options to full `parts[]`
 * so multi-question AskUserQuestion tool_uses roundtrip through replay
 * without losing parts 2..N.
 */
export interface OrphanAskUserQuestion {
  taskId: string;
  toolUseId: string;
  parts: InboxItemPart[];
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
      const parts = payload.parts.length > 0
        ? payload.parts
        : [{ question: "Question from Claude" }];
      orphans.push({
        taskId: m.taskId,
        toolUseId: m.toolUseId,
        parts,
        createdAt: m.timestamp,
      });
    }
  }
  return orphans;
}
