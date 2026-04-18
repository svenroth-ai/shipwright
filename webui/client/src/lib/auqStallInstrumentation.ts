/**
 * Pre/post AUQ-stall instrumentation — Sub-iterate B (assistant-ui
 * migration, 2026-04-17).
 *
 * Captures baseline behavior metrics around the AskUserQuestion submit
 * path so the renderer migration doesn't mask the latent "second AUQ
 * submit stalls silently" bug (14.14 Bug 2). The CLI-side root cause is
 * still unresolved; this module's goal is observability, not fix.
 *
 * What we capture per submit:
 *   - submit_ts          : wall-clock at click
 *   - answered_ts        : wall-clock when the mutation resolves
 *   - first_stream_ts    : wall-clock when turnStatus transitions back
 *                          into `streaming` after the answer
 *   - stall_ms           : (first_stream_ts - answered_ts) or null when
 *                          the next streaming tick never arrives.
 *
 * Logs to console via `console.info('[auq-stall-metrics]', data)` so the
 * browser devtools filter can isolate them. Also appends to an in-
 * memory ring buffer exposed as `window.__shipwright_auq_metrics` for
 * post-hoc inspection.
 *
 * Guarded by `shouldRunAuqInstrumentation()` — enabled in dev builds
 * unconditionally; prod builds only when `localStorage.AUQ_DEBUG=1`.
 */

export interface AuqStallRecord {
  taskKey: string;
  inboxId: string;
  submitAt: number;
  answeredAt: number | null;
  firstStreamAt: number | null;
  stallMs: number | null;
}

const BUFFER_LIMIT = 32;
const buffer: AuqStallRecord[] = [];

declare global {
  interface Window {
    __shipwright_auq_metrics?: AuqStallRecord[];
  }
}

export function shouldRunAuqInstrumentation(): boolean {
  if (typeof window === 'undefined') return false;
  const isDev = Boolean(
    (import.meta as unknown as { env?: { DEV?: boolean } }).env?.DEV,
  );
  if (isDev) return true;
  try {
    return window.localStorage.getItem('AUQ_DEBUG') === '1';
  } catch {
    return false;
  }
}

function push(record: AuqStallRecord): void {
  buffer.push(record);
  if (buffer.length > BUFFER_LIMIT) buffer.shift();
  if (typeof window !== 'undefined') {
    window.__shipwright_auq_metrics = [...buffer];
  }
}

/**
 * Register one submit. Returns two callbacks:
 *  - `onAnswered()` — fire when the `useAnswerInbox` mutation resolves.
 *  - `onFirstStream()` — fire on the first `streaming` turn-status
 *    transition after the submit.
 *
 * Safe to call the callbacks more than once; only the first call per
 * record has an effect. When both have fired, the record is pushed
 * to the ring buffer and console-logged.
 */
export function beginAuqSubmit(taskKey: string, inboxId: string): {
  onAnswered: () => void;
  onFirstStream: () => void;
} {
  if (!shouldRunAuqInstrumentation()) {
    return { onAnswered: () => {}, onFirstStream: () => {} };
  }

  const record: AuqStallRecord = {
    taskKey,
    inboxId,
    submitAt: performance.now(),
    answeredAt: null,
    firstStreamAt: null,
    stallMs: null,
  };

  let sealed = false;
  function seal(): void {
    if (sealed) return;
    if (record.answeredAt === null) return;
    // Stall resolves either on first_stream_ts OR when the caller
    // decides to give up. For now we seal only when both have landed;
    // an un-sealed record stays in memory with stallMs=null so a
    // debugging session can see which submits never fired a streaming
    // event — the smoking gun for the latent bug.
    if (record.firstStreamAt === null) return;
    record.stallMs = record.firstStreamAt - record.answeredAt;
    sealed = true;
    push({ ...record });
    // eslint-disable-next-line no-console
    console.info('[auq-stall-metrics]', record);
  }

  return {
    onAnswered: () => {
      if (record.answeredAt !== null) return;
      record.answeredAt = performance.now();
      // Expose even partial records so a session that never gets a
      // streaming event still shows up in the buffer.
      push({ ...record });
      seal();
    },
    onFirstStream: () => {
      if (record.firstStreamAt !== null) return;
      record.firstStreamAt = performance.now();
      seal();
    },
  };
}

/**
 * Drain the in-memory buffer. Used by a future debug panel / test
 * hook.
 */
export function getAuqStallBuffer(): readonly AuqStallRecord[] {
  return [...buffer];
}

/** Test-only helper to reset state between specs. */
export function __resetAuqStallBufferForTests(): void {
  buffer.length = 0;
  if (typeof window !== 'undefined') window.__shipwright_auq_metrics = [];
}
