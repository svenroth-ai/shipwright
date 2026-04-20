/*
 * Inbox — "best-effort" pending interactions across tracked external-launch
 * tasks. Round-3 plan integration explicitly labels the list as best-effort
 * because heuristic tool_use-without-tool_result correlation can false-
 * positive (long-running commands) and false-negative (plugin-owned
 * non-standard tool shapes). Users answer in their own chat client; webui
 * only surfaces the question here + offers dismiss.
 *
 * Iterate 3 section 05 — styling overhaul + project-filter integration:
 *   - Consumes the shared `useProjectFilter` hook (section 02) so the
 *     Sidebar's active project controls which session groups appear.
 *     Matches TaskBoard semantics: null = All Projects; unknown-task
 *     groups drop out under a specific filter and stay visible under
 *     All Projects.
 *   - Visual parity with `designs/screens/13-global-inbox.html`:
 *     3 px amber left strip (not a full amber background), neutral
 *     card body, right-aligned Answer + Dismiss buttons, muted
 *     session-UUID chip.
 *
 * Load-bearing testids (iterate-2 + section-05 Playwright specs depend):
 *   inbox-page, inbox-empty, inbox-session-<uuid>, inbox-item-<toolUseId>,
 *   dismiss-<toolUseId>.
 */

import { useMemo } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { askUserQuestionSummary } from "../external/session-parser";
import { useDismissInboxItem, useExternalInbox } from "../hooks/useExternalInbox";
import { useExternalTasks } from "../hooks/useExternalTasks";
import { useProjectFilter } from "../hooks/useProjectFilter";
import type { ExternalTask, InboxItem } from "../lib/externalApi";

export default function InboxPage() {
  const { data: items = [], isLoading } = useExternalInbox();
  const { data: tasks = [] } = useExternalTasks();
  const { activeProjectId } = useProjectFilter();
  const dismissMut = useDismissInboxItem();

  const tasksById = useMemo(() => {
    const m = new Map<string, ExternalTask>();
    for (const t of tasks) m.set(t.taskId, t);
    return m;
  }, [tasks]);

  const groups = useMemo(() => groupBySession(items), [items]);

  // Filter groups by the shared active-project selection. Matches
  // TaskBoard semantics (see TaskBoardPage): null = All Projects keeps
  // every group, including ones whose task has no projectId match
  // (orphans); a specific projectId drops groups whose task is from a
  // different project OR whose task record is missing entirely (server
  // de-sync).
  const visibleGroups = useMemo<SessionGroup[]>(() => {
    if (activeProjectId === null) return groups;
    return groups.filter((g) => {
      const task = tasksById.get(g.taskId);
      return task?.projectId === activeProjectId;
    });
  }, [groups, tasksById, activeProjectId]);

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

      {!isLoading && visibleGroups.length === 0 && (
        <div
          className="p-4 text-sm text-neutral-500"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-button)",
          }}
          data-testid="inbox-empty"
        >
          No pending interactions.
        </div>
      )}

      <div className="flex flex-col gap-3">
        {visibleGroups.map((g) => {
          const task = tasksById.get(g.taskId);
          return (
            <section
              key={g.sessionUuid}
              className="p-3"
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                boxShadow: "var(--shadow-card)",
              }}
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
                  <span className="font-mono text-[10px] text-neutral-500">
                    {g.sessionUuid.slice(0, 8)}
                  </span>
                </div>
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

/**
 * InboxRow — visual match to `designs/screens/13-global-inbox.html`.
 *
 *   ┌──┬──────────────────────────────────────────────┬──────────┐
 *   │▐▌│ AskUserQuestion  best-effort                 │ [Dismiss]│
 *   │▐▌│ question text …                              │ [Answer ]│
 *   │▐▌│ · option A  · option B                       │          │
 *   └──┴──────────────────────────────────────────────┴──────────┘
 *    ^3px amber left strip (border-left)             ^right-aligned CTAs
 *
 *   - Strip uses `--color-warning` (visual-guidelines token).
 *   - Answer is the primary CTA: Link to /tasks/<taskId>. Matches
 *     TerminalLaunchButton variant="inline" navigation target so
 *     muscle memory from iterate 2 still works.
 *   - Dismiss is a secondary button; same semantics as before.
 */
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
      className="flex items-start gap-3 p-3"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderLeft: "3px solid var(--color-warning, #D97706)",
        borderRadius: "var(--radius-button)",
      }}
      data-testid={`inbox-item-${item.toolUseId}`}
    >
      <AlertTriangle
        size={14}
        className="mt-0.5 shrink-0"
        style={{ color: "var(--color-warning, #D97706)" }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-neutral-700">
            {item.toolName}
          </span>
          <span className="rounded bg-neutral-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-neutral-600">
            best-effort
          </span>
        </div>
        {summary ? (
          <div className="mt-1">
            <div className="text-sm text-neutral-900">{summary.question}</div>
            {summary.options.length > 0 && (
              <ul className="mt-0.5 list-disc pl-4 text-xs text-neutral-600">
                {summary.options.map((o, i) => (
                  <li key={i}>{o}</li>
                ))}
              </ul>
            )}
            {summary.fallback && (
              <div className="mt-1 italic text-[10px] text-neutral-500">
                Question payload schema differed from expected.
              </div>
            )}
          </div>
        ) : (
          <pre className="mt-1 max-h-32 overflow-auto rounded bg-neutral-50 p-1 text-[10px]">
            {JSON.stringify(item.input, null, 2)}
          </pre>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={onDismiss}
          disabled={dismissing}
          className="border border-neutral-200 bg-white px-3 py-1 text-xs text-neutral-700 hover:bg-neutral-50 disabled:opacity-50"
          style={{ borderRadius: "var(--radius-button)" }}
          data-testid={`dismiss-${item.toolUseId}`}
        >
          Dismiss
        </button>
        <Link
          to={`/tasks/${item.taskId}`}
          className="inline-flex items-center bg-neutral-900 px-3 py-1 text-xs font-medium text-white hover:bg-neutral-700"
          style={{ borderRadius: "var(--radius-button)" }}
          data-testid={`answer-${item.toolUseId}`}
        >
          Answer
        </Link>
      </div>
    </div>
  );
}
