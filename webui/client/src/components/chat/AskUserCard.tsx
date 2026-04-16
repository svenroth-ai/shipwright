import { useMemo, useState } from 'react';
import { Check, AlertTriangle, Pause } from 'lucide-react';
import type { ChatMessage, TaskStatus } from '../../types';
import { useAnswerInbox, useInboxItem } from '../../hooks/useInbox';
import { useChatAwaiting } from '../../contexts/ChatAwaitingContext';
import { extractAskUserPayload } from '../../lib/askUserPayload';
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

  // Per-part local answer state, indexed by part index.
  // - For a single-select option list: the chosen option label.
  // - For a multi-select option list: comma-joined label string.
  // - For free text: the textarea value.
  const [partAnswers, setPartAnswers] = useState<Record<number, string>>({});
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
    setPartAnswers((prev) => ({ ...prev, [index]: value }));
  }

  function toggleMultiSelect(index: number, label: string) {
    setPartAnswers((prev) => {
      const current = prev[index] ?? '';
      const tokens = current.length > 0 ? current.split(', ').map((t) => t.trim()) : [];
      const exists = tokens.includes(label);
      const next = exists ? tokens.filter((t) => t !== label) : [...tokens, label];
      return { ...prev, [index]: next.join(', ') };
    });
  }

  // Every part needs a non-empty answer before Submit is enabled.
  const allAnswered = parts.every((_, idx) => {
    const value = partAnswers[idx];
    return typeof value === 'string' && value.trim().length > 0;
  });

  function handleSubmit() {
    if (!allAnswered) return;
    triggerAwaiting();
    const answers = parts.map((_, idx) => ({ index: idx, answer: partAnswers[idx] ?? '' }));
    answerMutation.mutate({ id: inboxId, answers });
    setLocalAnswered(true);
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

        {showNotBlockedBanner && (
          <div
            role="alert"
            data-testid="ask-user-not-blocked-banner"
            className="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />
              <div>
                <p className="font-medium">
                  Claude did not wait for your answer and kept generating.
                </p>
                <p className="mt-1 text-amber-800">
                  Your answer will still be sent as a tool_result. Depending on the turn
                  state, Claude may use it now or process it in the next turn.
                </p>
              </div>
            </div>
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
                const value = partAnswers[idx] ?? '';
                const options = part.options ?? [];
                const isMulti = part.allowMultiple === true;
                const selectedTokens = isMulti
                  ? (value.length > 0 ? value.split(', ').map((t) => t.trim()) : [])
                  : [];

                return (
                  <div key={idx} className="border-l-2 border-orange-200 pl-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-orange-600 mb-1">
                      {headerLabel}
                    </p>
                    <p className="text-sm font-semibold text-gray-900 mb-2">{part.question}</p>

                    {options.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {options.map((opt) => {
                          const active = isMulti ? selectedTokens.includes(opt) : value === opt;
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
                        value={value}
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
