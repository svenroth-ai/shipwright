/*
 * Inbox — "best-effort" pending interactions across tracked external-launch
 * tasks. Round-3 plan integration explicitly labels the list as best-effort
 * because heuristic tool_use-without-tool_result correlation can false-
 * positive (long-running commands) and false-negative (plugin-owned
 * non-standard tool shapes). Users answer in their own chat client; webui
 * only surfaces the question here + offers dismiss.
 */

import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { useDismissInboxItem, useExternalInbox } from "../hooks/useExternalInbox";

export default function InboxPage() {
  const { data: items = [], isLoading } = useExternalInbox();
  const dismissMut = useDismissInboxItem();

  return (
    <div className="flex h-full flex-col gap-4 p-4" data-testid="inbox-page">
      <header>
        <h1 className="text-xl font-semibold">Inbox</h1>
        <p className="text-sm text-neutral-500">
          Pending interactions (best-effort detection). Answer in your own terminal; dismiss false positives here.
        </p>
      </header>

      {isLoading && <div className="text-sm text-neutral-400">Loading…</div>}

      {!isLoading && items.length === 0 && (
        <div className="rounded border border-neutral-200 bg-white p-4 text-sm text-neutral-500" data-testid="inbox-empty">
          No pending interactions.
        </div>
      )}

      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <div
            key={item.toolUseId}
            className="flex items-start gap-3 rounded border border-amber-200 bg-amber-50 p-3"
            data-testid={`inbox-item-${item.toolUseId}`}
          >
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-700" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <Link
                  to={`/tasks/${item.taskId}`}
                  className="text-sm font-semibold text-amber-900 hover:underline"
                >
                  {item.taskTitle}
                </Link>
                <span className="rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-900">
                  best-effort
                </span>
              </div>
              <div className="text-xs text-amber-900">
                <span className="font-mono">{item.toolName}</span> — id {item.toolUseId}
              </div>
              <pre className="mt-1 overflow-x-auto rounded bg-white p-1 text-[11px]">
                {JSON.stringify(item.input, null, 2)}
              </pre>
            </div>
            <button
              type="button"
              onClick={() => dismissMut.mutate(item.toolUseId)}
              disabled={dismissMut.isPending}
              className="shrink-0 rounded border border-amber-300 bg-white px-2 py-1 text-xs text-amber-900 hover:bg-amber-100 disabled:opacity-50"
              data-testid={`dismiss-${item.toolUseId}`}
            >
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
