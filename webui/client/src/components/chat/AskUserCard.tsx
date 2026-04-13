import { useState } from 'react';
import { Check } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { useAnswerInbox } from '../../hooks/useInbox';
import { extractAskUserPayload } from '../../lib/askUserPayload';

interface AskUserCardProps {
  message: ChatMessage;
}

export function AskUserCard({ message }: AskUserCardProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [freetext, setFreetext] = useState('');
  const [isAnswered, setIsAnswered] = useState(false);
  const answerMutation = useAnswerInbox();

  const payload = extractAskUserPayload(message.toolInput);
  const question = payload.question || message.content || 'Question from Claude';
  const options = payload.options ?? [];
  const header = payload.header;
  const inboxId = String(
    (message.toolInput && typeof message.toolInput === 'object' && 'inboxId' in message.toolInput
      ? (message.toolInput as { inboxId?: unknown }).inboxId
      : undefined) ?? message.id,
  );

  function handleSubmit() {
    const answer = selectedOption ?? freetext.trim();
    if (!answer) return;

    answerMutation.mutate({ id: inboxId, answer });
    setIsAnswered(true);
  }

  return (
    <div className="flex justify-start">
      <div
        className="mr-auto max-w-[80%] bg-white border border-amber-200 border-l-4 border-l-amber-400 rounded-xl p-4 shadow-[var(--shadow-card)]"
      >
        {header && (
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-600 mb-1">{header}</p>
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
            <span>Answered: {selectedOption ?? freetext}</span>
          </div>
        )}
      </div>
    </div>
  );
}
