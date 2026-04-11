import { useState } from 'react';
import { Inbox, Check } from 'lucide-react';
import { useInbox, useAnswerInbox } from '../hooks/useInbox';
import { useProjects } from '../hooks/useProjects';
import { formatRelativeTime } from '../lib/formatTime';

export default function InboxPage() {
  const { data: items = [], isLoading } = useInbox();
  const { data: projects = [] } = useProjects();
  const answerMutation = useAnswerInbox();
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const pending = items.filter((i) => i.status === 'pending');
  const answered = items.filter((i) => i.status === 'answered');

  function handleAnswer(id: string) {
    const answer = answers[id]?.trim();
    if (!answer) return;
    answerMutation.mutate({ id, answer });
    setAnswers((prev) => { const next = { ...prev }; delete next[id]; return next; });
  }

  function getProjectName(projectId: string) {
    return projects.find((p) => p.id === projectId)?.name ?? 'Unknown';
  }

  // Group pending by project
  const pendingByProject = pending.reduce<Record<string, typeof pending>>((acc, item) => {
    const key = item.projectId;
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Inbox</h1>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
      ) : pending.length === 0 && answered.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <Inbox size={48} className="mx-auto mb-3 opacity-50" />
          <p className="text-lg">All caught up</p>
          <p className="text-sm">No questions waiting for your input</p>
        </div>
      ) : (
        <>
          {Object.entries(pendingByProject).map(([projectId, projectItems]) => (
            <div key={projectId} className="mb-8">
              <h2 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
                {getProjectName(projectId)} ({projectItems.length})
              </h2>
              <div className="space-y-3">
                {projectItems.map((item) => (
                  <div key={item.id} className="bg-white border border-[#e0dbd4] border-l-[3px] border-l-amber-500 rounded-xl p-4">
                    {/* Context pill */}
                    {item.context && (
                      <span className="inline-block px-2 py-0.5 text-[10px] font-semibold rounded-full bg-orange-50 text-orange-700 mb-2">
                        {item.context}
                      </span>
                    )}
                    <p className="text-sm font-medium text-gray-900 mb-2">{item.question}</p>
                    {item.options && item.options.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {item.options.map((opt) => (
                          <button
                            key={opt}
                            className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                              answers[item.id] === opt
                                ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                                : 'border-gray-300 bg-white hover:border-[var(--color-primary)]'
                            }`}
                            onClick={() => { setAnswers((prev) => ({ ...prev, [item.id]: opt })); }}
                          >
                            {opt}
                          </button>
                        ))}
                        {item.options.length > 0 && (
                          <span className="text-[10px] text-gray-300 self-center">or</span>
                        )}
                      </div>
                    )}
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={answers[item.id] ?? ''}
                        onChange={(e) => setAnswers((prev) => ({ ...prev, [item.id]: e.target.value }))}
                        placeholder="Type answer..."
                        className="flex-1 px-3 py-1.5 text-sm border border-[#e0dbd4] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
                        onKeyDown={(e) => e.key === 'Enter' && handleAnswer(item.id)}
                      />
                      <button
                        className="px-3 py-1.5 text-xs font-medium text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90"
                        onClick={() => handleAnswer(item.id)}
                      >
                        Answer
                      </button>
                    </div>
                    <div className="text-[10px] text-gray-400 mt-2">{formatRelativeTime(item.createdAt)}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {pending.length === 0 && (
            <div className="text-center py-8 text-gray-400 mb-6">
              <Inbox size={36} className="mx-auto mb-2 opacity-40" />
              <p className="text-sm">No pending questions</p>
            </div>
          )}

          {answered.length > 0 && (
            <div>
              <h2 className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Answered ({answered.length})
              </h2>
              <div className="space-y-2">
                {answered.map((item) => (
                  <div key={item.id} className="p-3 bg-gray-50 border border-gray-100 rounded-lg flex items-start gap-2">
                    <Check size={14} className="text-green-500 mt-0.5 shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm text-gray-700">{item.question}</p>
                      <p className="text-xs text-gray-500 mt-1">Answer: {item.answer}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
