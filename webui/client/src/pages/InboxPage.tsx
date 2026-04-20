/*
 * Inbox — "best-effort" pending interactions across tracked external-launch
 * tasks. Round-3 plan integration explicitly labels the list as best-effort
 * because heuristic tool_use-without-tool_result correlation can false-
 * positive (long-running commands) and false-negative (plugin-owned
 * non-standard tool shapes). Users answer in their own chat client; webui
 * only surfaces the question here + offers dismiss.
 */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { askUserQuestionSummary } from "../external/session-parser";
import { useDismissInboxItem, useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import type { ExternalTask, InboxItem } from "../lib/externalApi";
import { TerminalLaunchButton } from "../components/external/TerminalLaunchButton";

export default function InboxPage() {
  const { data: items = [], isLoading } = useExternalInbox();
  const { data: tasks = [] } = useExternalTasks();
  const dismissMut = useDismissInboxItem();

  const tasksById = useMemo(() => {
    const m = new Map<string, ExternalTask>();
    for (const t of tasks) m.set(t.taskId, t);
    return m;
  }, [tasks]);

  const groups = useMemo(() => groupBySession(items), [items]);

  return (
    <div className="flex h-full flex-col gap-4 p-4" data-testid="inbox-page">
      <header>
        <h1 className="text-xl font-semibold">Inbox</h1>
        <p className="text-sm text-neutral-500">
          Pending interactions (best-effort detection). Answer in your own
          terminal; dismiss false positives here.
        </p>
      </header>

      {isLoading && <div className="text-sm text-neutral-400">Loading…</div>}

      {!isLoading && items.length === 0 && (
        <div
          className="rounded border border-neutral-200 bg-white p-4 text-sm text-neutral-500"
          data-testid="inbox-empty"
        >
          No pending interactions.
        </div>
      )}

      <div className="flex flex-col gap-3">
        {groups.map((g) => {
          const task = tasksById.get(g.taskId);
          return (
            <section
              key={g.sessionUuid}
              className="rounded border border-neutral-200 bg-white p-3"
              data-testid={`inbox-session-${g.sessionUuid}`}
            >
              <header className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Link
                    to={`/tasks/${g.taskId}`}
                    className="text-sm font-semibold text-neutral-900 hover:underline"
                  >
                    {task?.title ?? g.taskTitle}
                  </Link>
                  <span className="font-mono text-[10px] text-neutral-400">
                    {g.sessionUuid.slice(0, 8)}
                  </span>
                </div>
                {task && <TerminalLaunchButton task={task} variant="inline" />}
              </header>
              <div className="flex flex-col gap-2">
                {g.items.map((item) => (
                  <InboxRow
                    key={item.toolUseId}
                    item={item}
                    onDismiss={() => dismissMut.mutate(item.toolUseId)}
                    dismissing={dismissMut.isPending}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

interface SessionGroup {
  sessionUuid: string;
  taskId: string;
  taskTitle: string;
  items: InboxItem[];
}

function groupBySession(items: InboxItem[]): SessionGroup[] {
  const groups = new Map<string, SessionGroup>();
  for (const item of items) {
    const existing = groups.get(item.sessionUuid);
    if (existing) {
      existing.items.push(item);
    } else {
      groups.set(item.sessionUuid, {
        sessionUuid: item.sessionUuid,
        taskId: item.taskId,
        taskTitle: item.taskTitle,
        items: [item],
      });
    }
  }
  return Array.from(groups.values());
}

function InboxRow({
  item,
  onDismiss,
  dismissing,
}: {
  item: InboxItem;
  onDismiss: () => void;
  dismissing: boolean;
}) {
  const isAUQ = item.toolName === "AskUserQuestion";
  const summary = isAUQ ? askUserQuestionSummary(item.input) : null;
  return (
    <div
      className="flex items-start gap-3 rounded border border-amber-200 bg-amber-50 p-2"
      data-testid={`inbox-item-${item.toolUseId}`}
    >
      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-700" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-amber-900">{item.toolName}</span>
          <span className="rounded bg-amber-200 px-1 py-0.5 text-[9px] font-semibold uppercase text-amber-900">
            best-effort
          </span>
        </div>
        {summary ? (
          <div className="mt-1">
            <div className="text-sm text-amber-900">{summary.question}</div>
            {summary.options.length > 0 && (
              <ul className="mt-0.5 list-disc pl-4 text-xs text-amber-800">
                {summary.options.map((o, i) => (
                  <li key={i}>{o}</li>
                ))}
              </ul>
            )}
            {summary.fallback && (
              <div className="mt-1 italic text-[10px] text-amber-700">
                Question payload schema differed from expected.
              </div>
            )}
          </div>
        ) : (
          <pre className="mt-1 max-h-32 overflow-auto rounded bg-white p-1 text-[10px]">
            {JSON.stringify(item.input, null, 2)}
          </pre>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        disabled={dismissing}
        className="shrink-0 rounded border border-amber-300 bg-white px-2 py-1 text-xs text-amber-900 hover:bg-amber-100 disabled:opacity-50"
        data-testid={`dismiss-${item.toolUseId}`}
      >
        Dismiss
      </button>
    </div>
  );
}
