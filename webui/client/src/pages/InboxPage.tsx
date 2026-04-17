import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Inbox, Check, AlertTriangle } from 'lucide-react';
import { useInbox, useAnswerInbox } from '../hooks/useInbox';
import { useProjects } from '../hooks/useProjects';
import { formatRelativeTime } from '../lib/formatTime';
import type { InboxItem } from '../types/inbox';

/**
 * Iterate 14.2 — multi-part inbox list.
 *
 * Each `InboxItem` now contains a `parts[]` array. For single-part items
 * the UI is unchanged. For multi-part items we surface a "{N} questions"
 * badge in the list and render an inline accordion with one input per
 * part. Submit is gated until every part has a non-empty answer, and
 * clicking it sends the full `answers` array to the backend in one POST.
 */
export default function InboxPage() {
  const { data: items = [], isLoading } = useInbox();
  const { data: projects = [] } = useProjects();
  const answerMutation = useAnswerInbox();
  const navigate = useNavigate();

  // Iterate 14.7.1 — clicking an inbox item's outer card navigates to the
  // owning task's detail view. The `?focus=chat-bottom` query string is
  // interpreted by TaskDetailPage → ChatPanel to scroll to the newest
  // message immediately, so the user lands on the question in context
  // rather than the top of an empty chat. Inner interactive elements
  // (option buttons, Answer button, inputs) stopPropagation so they don't
  // accidentally fire the navigation.
  //
  // Iterate 14.14 — the original path `/projects/:id/tasks/:taskId` hit
  // react-router's default 404 ErrorBoundary because the router only
  // defines `/tasks/:taskId`. TaskDetailPage resolves projectId from the
  // task object itself (useTasks() + t.id lookup), so the prefix is not
  // needed.
  function handleOpenTask(item: InboxItem) {
    navigate(`/tasks/${item.taskId}?focus=chat-bottom`);
  }

  function stop(e: React.MouseEvent | React.KeyboardEvent) {
    e.stopPropagation();
  }
  // Per-item, per-part-index local answer state.
  const [drafts, setDrafts] = useState<Record<string, Record<number, string>>>({});

  const pending = items.filter((i) => i.status === 'pending');
  const answered = items.filter((i) => i.status === 'answered');

  function setDraft(itemId: string, partIndex: number, value: string) {
    setDrafts((prev) => ({
      ...prev,
      [itemId]: { ...(prev[itemId] ?? {}), [partIndex]: value },
    }));
  }

  function clearDraft(itemId: string) {
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[itemId];
      return next;
    });
  }

  function isItemReady(item: InboxItem): boolean {
    const draft = drafts[item.id] ?? {};
    return item.parts.every((_, idx) => {
      const v = draft[idx];
      return typeof v === 'string' && v.trim().length > 0;
    });
  }

  function handleAnswer(item: InboxItem) {
    if (!isItemReady(item)) return;
    const draft = drafts[item.id] ?? {};
    const answers = item.parts.map((_, idx) => ({ index: idx, answer: draft[idx] ?? '' }));
    answerMutation.mutate({ id: item.id, answers });
    clearDraft(item.id);
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
                {projectItems.map((item) => {
                  const draft = drafts[item.id] ?? {};
                  const ready = isItemReady(item);
                  return (
                    <div
                      key={item.id}
                      role="button"
                      tabIndex={0}
                      data-testid={`inbox-item-${item.id}`}
                      onClick={() => handleOpenTask(item)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleOpenTask(item);
                        }
                      }}
                      className="bg-white border border-[#e0dbd4] border-l-[3px] border-l-amber-500 rounded-xl p-4 cursor-pointer hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/30"
                    >
                      <div className="flex items-center gap-2 mb-2">
                        {item.notBlocked && (
                          <span
                            role="img"
                            aria-label="Claude did not wait for your answer"
                            title="Claude did not wait for your answer and kept generating"
                            data-testid="inbox-not-blocked-icon"
                            className="inline-flex items-center text-amber-600"
                          >
                            <AlertTriangle size={14} />
                          </span>
                        )}
                        {item.parts.length > 1 && (
                          <span className="inline-block px-2 py-0.5 text-[10px] font-semibold rounded-full bg-orange-50 text-orange-700">
                            {item.parts.length} questions
                          </span>
                        )}
                      </div>

                      <div className="space-y-3">
                        {item.parts.map((part, idx) => {
                          const headerLabel = part.header && part.header.trim().length > 0
                            ? part.header.trim()
                            : `Question ${idx + 1}`;
                          const value = draft[idx] ?? '';
                          const options = part.options ?? [];
                          const isMulti = part.allowMultiple === true;
                          const tokens = isMulti
                            ? (value.length > 0 ? value.split(', ').map((t) => t.trim()) : [])
                            : [];

                          return (
                            <div key={idx} className={item.parts.length > 1 ? 'border-l-2 border-orange-200 pl-3' : ''}>
                              {item.parts.length > 1 && (
                                <p className="text-[10px] font-semibold uppercase tracking-wider text-orange-600 mb-1">
                                  {headerLabel}
                                </p>
                              )}
                              <p className="text-sm font-medium text-gray-900 mb-2">{part.question}</p>
                              {options.length > 0 && (
                                <div className="flex flex-wrap gap-2 mb-2">
                                  {options.map((opt) => {
                                    const active = isMulti ? tokens.includes(opt) : value === opt;
                                    return (
                                      <button
                                        key={opt}
                                        type="button"
                                        className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                                          active
                                            ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                                            : 'border-gray-300 bg-white hover:border-[var(--color-primary)]'
                                        }`}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          if (isMulti) {
                                            const next = tokens.includes(opt)
                                              ? tokens.filter((t) => t !== opt)
                                              : [...tokens, opt];
                                            setDraft(item.id, idx, next.join(', '));
                                          } else {
                                            setDraft(item.id, idx, opt);
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
                                <input
                                  type="text"
                                  value={value}
                                  onChange={(e) => setDraft(item.id, idx, e.target.value)}
                                  placeholder="Type answer..."
                                  className="w-full px-3 py-1.5 text-sm border border-[#e0dbd4] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
                                  onClick={stop}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' && item.parts.length === 1) handleAnswer(item);
                                  }}
                                />
                              )}
                            </div>
                          );
                        })}
                      </div>

                      <div className="mt-3 flex items-center justify-between gap-2">
                        <div className="text-[10px] text-gray-400">{formatRelativeTime(item.createdAt)}</div>
                        <button
                          type="button"
                          disabled={!ready}
                          data-testid={`inbox-answer-${item.id}`}
                          className="px-3 py-1.5 text-xs font-medium text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleAnswer(item);
                          }}
                        >
                          Answer
                        </button>
                      </div>
                    </div>
                  );
                })}
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
                      {item.parts.map((p, idx) => (
                        <div key={idx} className={idx > 0 ? 'mt-1.5' : ''}>
                          <p className="text-sm text-gray-700">{p.question}</p>
                          <p className="text-xs text-gray-500">Answer: {p.answer ?? '(skipped)'}</p>
                        </div>
                      ))}
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
