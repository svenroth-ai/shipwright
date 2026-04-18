import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, AlertTriangle, Pause } from 'lucide-react';
import type { ChatMessage, TaskStatus } from '../../types';
import { useAnswerInbox, useInboxItem } from '../../hooks/useInbox';
import { useChatAwaiting } from '../../contexts/ChatAwaitingContext';
import { useTurnStatus } from '../../hooks/useTurnStatus';
import { extractAskUserPayload } from '../../lib/askUserPayload';
import { beginAuqSubmit } from '../../lib/auqStallInstrumentation';
import type { InboxItemPart } from '../../types/inbox';

interface AskUserCardProps {
  message: ChatMessage;
  /**
   * Iterate 14.10 — task lifecycle context threaded down from ChatPanel
   * via ChatMessage. Used to render the pause indicator + Resume button
   * at the top of the card when the task was interrupted while a
   * pending AskUserQuestion was waiting on disk.
   *
   * The same conditions drive the TaskCard pause icon
   * (status=orphaned + resumable orphanReason + claudeSessionId), so
   * the chat view stays consistent with the kanban affordance.
   */
  taskStatus?: TaskStatus;
  orphanReason?: string;
  claudeSessionId?: string;
  /** Click handler for the Resume button. Wired to useResumeTask in
   *  ChatPanel. Omitted in tests that don't exercise resume. */
  onResume?: () => void;
}

/**
 * Iterate 14.2 — Accordion rendering for multi-question AskUserQuestion.
 *
 * Claude CLI always emits a `questions: Question[]` array, occasionally
 * with 2-4 entries in one tool_use call. We render every part vertically
 * (no expand/collapse — they're all visible at once) and gate Submit on
 * having an answer for EVERY part. On submit we send the full answers
 * array to the backend, which joins them into a single tool_result.
 */
export function AskUserCard({
  message,
  taskStatus,
  orphanReason,
  claudeSessionId,
  onResume,
}: AskUserCardProps) {
  const answerMutation = useAnswerInbox();
  const { triggerAwaiting } = useChatAwaiting();

  // Iterate 14.10 — derive interrupted state. Same gate the TaskCard uses
  // (board/TaskCard.tsx ~line 59) so the chat view doesn't disagree with
  // the kanban affordance. The Resume button is hidden if onResume is
  // not wired (lets unit tests render the card without a router/hook
  // pulling in a query client).
  const isInterrupted =
    taskStatus === 'orphaned' &&
    (orphanReason === 'stale_on_startup' || orphanReason === 'user_interrupted') &&
    !!claudeSessionId;

  const payload = useMemo(() => extractAskUserPayload(message.toolInput), [message.toolInput]);
  const parts: InboxItemPart[] = payload.parts.length > 0
    ? payload.parts
    : [{ question: message.content || 'Question from Claude' }];

  // Per-part local answer state. Iterate askuser-multiselect-bugs
  // (2026-04-18): split the previous single `Record<number, string>`
  // into two maps so multi-select labels that *contain* `", "` (e.g.
  // "Grundfunktionen (Erstellen, Abhaken, Löschen)") no longer get
  // shredded by `split(', ')`. The joined-string representation was
  // convenient for the API payload but round-trip-broken on parse.
  //   textAnswers  : Record<number, string>   — single-select pick, or
  //                                             free-text textarea.
  //   multiAnswers : Record<number, string[]> — multi-select labels, in
  //                                             selection order. Joined
  //                                             with `", "` at submit
  //                                             time only.
  const [textAnswers, setTextAnswers] = useState<Record<number, string>>({});
  const [multiAnswers, setMultiAnswers] = useState<Record<number, string[]>>({});
  const [localAnswered, setLocalAnswered] = useState(false);

  // Use the Anthropic toolUseId as the inbox item id so it survives
  // refreshes and correlates 1:1 with the persisted server-side entry.
  // Fall back to message.id for legacy messages without a toolUseId.
  const inboxId = message.toolUseId ?? message.id;

  // Hydrate "answered" state from persisted server inbox so refresh keeps
  // the green "Answered" display.
  const persistedItem = useInboxItem(inboxId);
  const isAnswered = localAnswered || persistedItem?.status === 'answered';
  // Iterate 14.5 — amber warning banner when Claude ignored the
  // constitution rule and kept generating after AskUserQuestion without
  // waiting for the user's answer. Flag lives on the persisted inbox
  // item (`notBlocked`), seeded from the REST payload and live-updated
  // by the `inbox:flag_not_blocked` SSE handler. Reconnect-resilient.
  const showNotBlockedBanner = persistedItem?.notBlocked === true;

  function setAnswer(index: number, value: string) {
    setTextAnswers((prev) => ({ ...prev, [index]: value }));
  }

  function toggleMultiSelect(index: number, label: string) {
    setMultiAnswers((prev) => {
      const current = prev[index] ?? [];
      const exists = current.includes(label);
      const next = exists ? current.filter((t) => t !== label) : [...current, label];
      return { ...prev, [index]: next };
    });
  }

  /**
   * Build the final string answer for a part, indexed by part index.
   * Multi-select parts join their array with `", "` — the API payload
   * shape is unchanged (parts[n].answer is still a string). Single-
   * select / text parts pass through from textAnswers.
   */
  function answerFor(index: number, part: InboxItemPart): string {
    if (part.allowMultiple === true) {
      const arr = multiAnswers[index] ?? [];
      return arr.join(', ');
    }
    return textAnswers[index] ?? '';
  }

  // Every part needs a non-empty answer before Submit is enabled.
  const allAnswered = parts.every((part, idx) => {
    const value = answerFor(idx, part);
    return value.trim().length > 0;
  });

  // Iterate 14.14 — Bug 2. The answer mutation was previously fire-and-
  // forget. If the POST failed (e.g. "Process no longer running" 400 after
  // a respawn, or a transient 5xx), the card still flipped to "Answered"
  // and the triggerAwaiting() spinner stayed on forever because the turn
  // status never transitioned to `streaming`. Capture the error locally
  // so the user can see *why* nothing happened and retry.
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Sub-iterate B — AUQ-stall observability. `stallHooksRef` holds the
  // callbacks returned by beginAuqSubmit so the effect watching
  // turn.status can fire onFirstStream() exactly once per submit.
  const stallHooksRef = useRef<{
    onAnswered: () => void;
    onFirstStream: () => void;
  } | null>(null);
  const turn = useTurnStatus(message.taskId ? (message.taskId.split('::')[0] ?? '') : '', message.taskId ?? '');
  useEffect(() => {
    if (turn.status === 'streaming' && stallHooksRef.current) {
      stallHooksRef.current.onFirstStream();
      stallHooksRef.current = null;
    }
  }, [turn.status]);

  function handleSubmit() {
    if (!allAnswered) return;
    setSubmitError(null);
    triggerAwaiting();
    // Flip the optimistic "Answered" state BEFORE firing the mutation so
    // the onError rollback (which may run synchronously in some test
    // doubles and asynchronously in production) always lands *after* the
    // optimistic flip. Otherwise a sync onError would be overwritten by
    // a later setLocalAnswered(true).
    setLocalAnswered(true);
    const answers = parts.map((part, idx) => ({ index: idx, answer: answerFor(idx, part) }));
    const hooks = beginAuqSubmit(message.taskId ?? '', inboxId);
    stallHooksRef.current = hooks;
    answerMutation.mutate(
      { id: inboxId, answers },
      {
        onSuccess: () => {
          hooks.onAnswered();
        },
        onError: (err) => {
          // Roll back the optimistic "Answered" state so the user can
          // correct + re-submit. The triggerAwaiting() spinner will also
          // clear on the next turn-status transition (or can be dismissed
          // by closing the card).
          setLocalAnswered(false);
          const msg = err instanceof Error ? err.message : 'Failed to submit answer';
          setSubmitError(msg);
          // Still record the answered timestamp so the stall-metrics
          // log shows the error path as a distinct trace.
          hooks.onAnswered();
          stallHooksRef.current = null;
        },
      },
    );
  }

  return (
    <div className="flex justify-start">
      <div className="mr-auto max-w-[80%] bg-white border border-orange-300 border-l-4 border-l-orange-500 rounded-xl p-4 shadow-[var(--shadow-card)]">
        {/* Iterate 14.10 — interrupted-task pause indicator + Resume button.
            Renders at the top of the card so the chat view matches the
            TaskCard pause icon on the kanban; without this the user sees
            the AskUserQuestion but no way to know the task is dead. */}
        {isInterrupted && (
          <div
            data-testid="ask-user-pause-indicator"
            className="flex items-center gap-2 mb-3 p-2 rounded bg-amber-50 border border-amber-200"
          >
            <Pause size={16} className="text-amber-700 shrink-0" />
            <span className="text-xs text-amber-900 flex-1">
              Task interrupted — resume to continue
            </span>
            {onResume && (
              <button
                type="button"
                data-testid="ask-user-resume-button"
                onClick={onResume}
                className="px-2 py-1 text-xs bg-amber-700 text-white rounded hover:bg-amber-800"
              >
                Resume
              </button>
            )}
          </div>
        )}

        {submitError && (
          <div
            role="alert"
            data-testid="ask-user-submit-error"
            className="mb-3 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-600" />
              <div className="flex-1">
                <p className="font-medium">Submit failed</p>
                <p className="mt-1 text-red-800">{submitError}</p>
              </div>
              <button
                type="button"
                className="text-red-500 hover:text-red-700"
                onClick={() => setSubmitError(null)}
                aria-label="Dismiss error"
              >
                x
              </button>
            </div>
          </div>
        )}

        {showNotBlockedBanner && (
          // Iterate askuser-multiselect-bugs (2026-04-18) — banner
          // slimmed. Previously `p-3 + text-sm + size=16` — visually
          // dominant + distracting from the actual question. Now a
          // compact one-liner with a tiny info icon. Same testid,
          // same role, same message intent (user must still know
          // Claude didn't wait); just less loud.
          <div
            role="status"
            data-testid="ask-user-not-blocked-banner"
            className="mb-2 flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-800"
          >
            <AlertTriangle size={11} className="shrink-0 text-amber-600" />
            <span>
              Claude kept generating — your answer will still be sent.
            </span>
          </div>
        )}

        {parts.length > 1 && (
          <p className="text-[11px] font-semibold uppercase tracking-wider text-orange-600 mb-2">
            {parts.length} questions
          </p>
        )}

        {!isAnswered ? (
          <>
            <div className="space-y-4">
              {parts.map((part, idx) => {
                const headerLabel = part.header && part.header.trim().length > 0
                  ? part.header.trim()
                  : `Question ${idx + 1}`;
                const options = part.options ?? [];
                const isMulti = part.allowMultiple === true;
                const textValue = textAnswers[idx] ?? '';
                const selectedTokens = isMulti ? (multiAnswers[idx] ?? []) : [];

                return (
                  <div key={idx} className="border-l-2 border-orange-200 pl-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-orange-600 mb-1">
                      {headerLabel}
                    </p>
                    <p className="text-sm font-semibold text-gray-900 mb-2">{part.question}</p>

                    {options.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {options.map((opt) => {
                          const active = isMulti
                            ? selectedTokens.includes(opt)
                            : textValue === opt;
                          return (
                            <button
                              key={opt}
                              type="button"
                              className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                                active
                                  ? 'bg-[var(--color-primary)] text-white border-[var(--color-primary)]'
                                  : 'bg-white border-gray-300 hover:border-[var(--color-primary)]'
                              }`}
                              onClick={() => {
                                if (isMulti) {
                                  toggleMultiSelect(idx, opt);
                                } else {
                                  setAnswer(idx, opt);
                                }
                              }}
                            >
                              {opt}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {!isMulti && options.length === 0 && (
                      <textarea
                        value={textValue}
                        onChange={(e) => setAnswer(idx, e.target.value)}
                        placeholder="Type your answer..."
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
                      />
                    )}
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              disabled={!allAnswered}
              onClick={handleSubmit}
              className="mt-4 px-4 py-1.5 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit Answer
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2 text-sm text-green-700">
            <Check size={16} />
            <span>Answered ({parts.length} {parts.length === 1 ? 'question' : 'questions'})</span>
          </div>
        )}
      </div>
    </div>
  );
}
