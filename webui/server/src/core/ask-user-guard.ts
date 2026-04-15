import type { ChatMessage } from "../../../client/src/types/chat.js";

/**
 * Iterate 14.5 — per-turn AskUserQuestion guard.
 *
 * Tracks which AskUserQuestion `tool_use_id`s are still "open" (no
 * matching tool_result yet) and classifies each incoming content block
 * to decide when to flag an open question as `notBlocked`. Lives in its
 * own module so the inline logic in index.ts stays simple AND so we can
 * unit-test the state machine without spawning a Claude process.
 *
 * Detection rules:
 *   - AskUserQuestion tool_use → register the tool_use_id.
 *   - Non-AskUserQuestion tool_use after a registered AUQ → flag all
 *     registered ids with reason "continued".
 *   - Assistant text / thinking block after a registered AUQ → flag
 *     all registered ids with reason "continued".
 *   - tool_result with a matching tool_use_id → deregister that id
 *     (answered correctly).
 *   - `result` event (turn end) → flag all remaining registered ids
 *     with reason "turn_ended" and clear the turn.
 *
 * The guard does NOT mutate any inbox state — it only reports the
 * decisions. The caller (index.ts adapter callback) applies them via
 * `inboxManager.setNotBlocked` and `sseManager.broadcast`.
 */

export type NotBlockedReason = "continued" | "turn_ended";

export interface NotBlockedFlag {
  toolUseId: string;
  reason: NotBlockedReason;
}

export interface GuardDecision {
  /** tool_use_ids that should be newly registered as pending AUQ. */
  register: string[];
  /** ids that should be flagged as notBlocked (with reason). */
  flag: NotBlockedFlag[];
  /** ids that should be removed from the pending set (answered). */
  resolve: string[];
  /** true if a turn end was observed — caller should clear the set. */
  turnEnded: boolean;
}

/**
 * Classify one ordered batch of extracted ChatMessage content blocks
 * against the current per-task pending set. Pure — does not mutate
 * `pending`. Caller applies the returned decision.
 */
export function classifyContentBlocks(
  chatMessages: ChatMessage[],
  pending: ReadonlySet<string>,
): GuardDecision {
  const decision: GuardDecision = {
    register: [],
    flag: [],
    resolve: [],
    turnEnded: false,
  };

  // Work with a live projection so we respect intra-batch ordering:
  // an AUQ registered earlier in this batch should be flagged by a
  // text block later in the same batch.
  const live = new Set<string>(pending);

  for (const msg of chatMessages) {
    if (msg.type === "tool_use" && msg.toolName === "AskUserQuestion") {
      if (msg.toolUseId) {
        decision.register.push(msg.toolUseId);
        live.add(msg.toolUseId);
      }
      continue;
    }

    if (msg.type === "tool_use") {
      // Non-AUQ tool_use after an AUQ → continuation.
      if (live.size > 0) {
        for (const id of live) {
          decision.flag.push({ toolUseId: id, reason: "continued" });
        }
      }
      continue;
    }

    if (msg.type === "assistant" || msg.type === "thinking") {
      if (live.size > 0) {
        for (const id of live) {
          decision.flag.push({ toolUseId: id, reason: "continued" });
        }
      }
      continue;
    }

    if (msg.type === "tool_result") {
      if (msg.toolUseId && live.has(msg.toolUseId)) {
        decision.resolve.push(msg.toolUseId);
        live.delete(msg.toolUseId);
      }
      continue;
    }

    if (msg.type === "result") {
      if (live.size > 0) {
        for (const id of live) {
          decision.flag.push({ toolUseId: id, reason: "turn_ended" });
        }
        live.clear();
      }
      decision.turnEnded = true;
      continue;
    }
  }

  return decision;
}
