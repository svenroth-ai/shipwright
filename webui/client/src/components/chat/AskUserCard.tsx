import { useState } from 'react';
import { Check } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { useAnswerInbox, useInboxItem } from '../../hooks/useInbox';
import { useChatAwaiting } from '../../contexts/ChatAwaitingContext';
import { extractAskUserPayload } from '../../lib/askUserPayload';

interface AskUserCardProps {
  message: ChatMessage;
}

export function AskUserCard({ message }: AskUserCardProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [freetext, setFreetext] = useState('');
  const [localAnswered, setLocalAnswered] = useState(false);
  const answerMutation = useAnswerInbox();
  const { triggerAwaiting } = useChatAwaiting();

  const payload = extractAskUserPayload(message.toolInput);
  const question = payload.question || message.content || 'Question from Claude';
  const options = payload.options ?? [];
  const header = payload.header;

  // Use the Anthropic toolUseId (propagated by iterate-2's parser + iterate-5's
  // streaming hook) as the inbox item id so it survives page refreshes and
  // correlates 1:1 with the persisted server-side inbox entry. Fall back to
  // message.id for legacy messages that don't have a toolUseId. See ADR-018.
  const inboxId = message.toolUseId ?? message.id;

  // Hydrate "answered" state from the persisted server inbox so refresh keeps
  // the green "Answered: X" display.
  const persistedItem = useInboxItem(inboxId);
  const isAnswered = localAnswered || persistedItem?.status === 'answered';
  const persistedAnswer = persistedItem?.answer;

  function handleSubmit() {
    const answer = selectedOption ?? freetext.trim();
    if (!answer) return;

    // Fire the awaiting indicator immediately so ChatPanel can show
    // "Thinking…" before Claude CLI's first NDJSON event arrives.
    // See iterate 7 spec — closes the 2-3s latency gap on inbox replies.
    triggerAwaiting();
    answerMutation.mutate({ id: inboxId, answer });
    setLocalAnswered(true);
  }

  return (
    <div className="flex justify-start">
      <div
        className="mr-auto max-w-[80%] bg-white border border-orange-300 border-l-4 border-l-orange-500 rounded-xl p-4 shadow-[var(--shadow-card)]"
      >
        {header && (
          <p className="text-[11px] font-semibold uppercase tracking-wider text-orange-600 mb-1">{header}</p>
        )}
        <p className="text-sm font-semibold text-gray-900 mb-3">{question}</p>

        {!isAnswered ? (
          <>
            {options.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {options.map((opt) => (
                  <button
                    key={opt}
                    className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                      selectedOption === opt
                        ? 'bg-[var(--color-primary)] text-white border-[var(--color-primary)]'
                        : 'bg-white border-gray-300 hover:border-[var(--color-primary)]'
                    }`}
                    onClick={() => { setSelectedOption(opt); setFreetext(''); }}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            )}

            <textarea
              value={freetext}
              onChange={(e) => { setFreetext(e.target.value); setSelectedOption(null); }}
              placeholder="Type your answer..."
              rows={2}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 mb-2"
            />

            <button
              disabled={!selectedOption && !freetext.trim()}
              onClick={handleSubmit}
              className="px-4 py-1.5 text-sm font-medium text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit Answer
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2 text-sm text-green-700">
            <Check size={16} />
            <span>Answered: {persistedAnswer ?? selectedOption ?? freetext}</span>
          </div>
        )}
      </div>
    </div>
  );
}
