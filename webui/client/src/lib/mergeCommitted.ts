import type { ChatMessage } from '../types';

/**
 * Iterate 13 / Phase 0 precondition: when SSE broadcasts carry fully-extracted
 * ChatMessages with stable ids (same id space as REST GET /chat), the client
 * can dedupe by id at merge time instead of refetching history.
 *
 * Pure function: merge a single incoming ChatMessage into an existing array,
 * deduping by id and preserving sorted order by `(timestamp, insertion-index)`.
 *
 * Rules:
 * - If the id already exists in `prev`, the incoming message replaces it.
 *   In development, a content diff on the same id logs a warning — this lets
 *   legitimate server fix-ups through while surfacing accidental replays.
 * - Otherwise the message is inserted at the position that keeps the array
 *   sorted by `Date.parse(timestamp)`, with stable insertion order for ties.
 *
 * Never mutates `prev`; always returns a fresh array (TanStack Query requires
 * referential-identity changes to trigger re-renders).
 */
export function mergeCommitted(
  prev: ChatMessage[] | undefined,
  incoming: ChatMessage,
): ChatMessage[] {
  const base = prev ?? [];
  const existingIdx = base.findIndex((m) => m.id === incoming.id);

  if (existingIdx >= 0) {
    if (import.meta.env.DEV && base[existingIdx].content !== incoming.content) {
      console.warn(
        '[mergeCommitted] same-id content diff for',
        incoming.id,
        { was: base[existingIdx].content, now: incoming.content },
      );
    }
    const next = base.slice();
    next[existingIdx] = incoming;
    return next;
  }

  const incomingT = Date.parse(incoming.timestamp);
  // Walk backwards to find the last element whose timestamp is <= incoming's;
  // insert after it. For equal timestamps this preserves existing-first order,
  // which mirrors how chatStore.load sorts history server-side.
  let insertAt = 0;
  for (let i = base.length - 1; i >= 0; i--) {
    if (Date.parse(base[i].timestamp) <= incomingT) {
      insertAt = i + 1;
      break;
    }
  }
  // Special case: if the loop never matched (incoming is older than all) and
  // base is non-empty, insertAt stays 0 — which is correct.
  if (base.length > 0 && Date.parse(base[0].timestamp) > incomingT) {
    insertAt = 0;
  }

  const next = base.slice();
  next.splice(insertAt, 0, incoming);
  return next;
}
