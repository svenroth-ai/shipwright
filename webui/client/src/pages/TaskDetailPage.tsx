/*
 * TaskDetailPage — thin composition shell for the 3-pane task detail
 * surface (iterate 3 section 04, AD-03.06 + FR-03.30..36; visual rebuild
 * in iterate 3.7b-3 / Phase B3).
 *
 * Multi-file viewer: `selectedPaths` is the tab list (dedup order
 * preserving). `activePath` is the currently-rendered file in the right
 * pane. Clicking a folder-tree row adds the path to the array (if new)
 * and activates it; closing a tab from the ViewerTabBar removes it, then
 * falls back to the last-remaining path or `null` when the array empties.
 *
 * Transcript pane header: derives user-facing counts (events, tool uses,
 * pending AskUserQuestion) from the parsed transcript — the debug
 * status/fingerprint/size display moved behind the header's "Show
 * session details" toggle.
 *
 * Regression guards:
 *   - No chat composer (DO-NOT #3).
 *   - No webui-initiated `claude --resume` (DO-NOT #5).
 */

import { useCallback, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { useExternalTask } from "../hooks/useExternalTasks";
import { useTaskTranscript } from "../hooks/useTaskTranscript";
import { BubbleTranscript } from "../components/external/BubbleTranscript";
import { TaskDetailHeader } from "../components/external/TaskDetailHeader";
import { TaskDetailThreePane } from "../components/external/TaskDetailThreePane";
import { FolderTree } from "../components/external/FolderTree";
import { SmartViewer } from "../components/external/SmartViewer";
import { ViewerTabBar } from "../components/external/SmartViewer/ViewerTabBar";
import { parseSessionJsonl, toolUses } from "../external/session-parser";

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, error } = useExternalTask(taskId);
  const transcript = useTaskTranscript(taskId ?? null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);

  const handleSelect = useCallback((path: string) => {
    setSelectedPaths((prev) => (prev.includes(path) ? prev : [...prev, path]));
    setActivePath(path);
  }, []);

  const handleCloseTab = useCallback((path: string) => {
    setSelectedPaths((prev) => {
      const next = prev.filter((p) => p !== path);
      // If the closed tab was active, fall back to the last remaining tab
      // (or null when the list empties).
      setActivePath((prevActive) => {
        if (prevActive !== path) return prevActive;
        return next.length > 0 ? next[next.length - 1] : null;
      });
      return next;
    });
  }, []);

  // Derived transcript stats, used by the center-pane header.
  const transcriptStats = useMemo(() => {
    if (!transcript.content) {
      return { events: 0, toolUses: 0, pending: 0 };
    }
    const { events } = parseSessionJsonl(transcript.content);
    let tools = 0;
    for (const e of events) {
      if (e.kind === "assistant") {
        tools += toolUses(e).length;
      }
    }
    const pending = task?.inbox?.pendingToolUseIds?.length ?? 0;
    return { events: events.length, toolUses: tools, pending };
  }, [transcript.content, task?.inbox?.pendingToolUseIds]);

  if (error) {
    return (
      <div
        className="p-4 text-sm text-[var(--color-error,#DC2626)]"
        data-testid="task-detail-error"
      >
        Error loading task: {String(error)}
      </div>
    );
  }
  if (!task) {
    return (
      <div
        className="p-4 text-sm text-[var(--color-muted,#6b7280)]"
        data-testid="task-detail-loading"
      >
        Loading…
      </div>
    );
  }

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      data-testid="task-detail-page"
      style={{ background: "var(--color-bg, #f5f0eb)" }}
    >
      <TaskDetailHeader task={task} />

      <div className="min-h-0 flex-1">
        <TaskDetailThreePane
          left={
            <FolderTree
              projectId={task.projectId}
              selectedPath={activePath}
              onSelect={handleSelect}
            />
          }
          center={
            <section
              className="flex h-full min-h-0 flex-col"
              style={{ background: "var(--color-bg, #f5f0eb)" }}
              data-testid="task-detail-transcript"
            >
              <div
                className="flex min-h-[40px] items-center gap-3 border-b border-[var(--color-border,#e0dbd4)] px-4 py-2 text-[11px]"
                style={{
                  background: "var(--color-surface, #ffffff)",
                  color: "var(--color-muted, #6b7280)",
                }}
                data-testid="task-detail-transcript-header"
              >
                <span className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="inline-block h-[6px] w-[6px] rounded-full bg-[var(--color-info,#3B82F6)]"
                  />
                  <span data-testid="transcript-stat-events">
                    {transcriptStats.events} events
                  </span>
                </span>
                <span aria-hidden="true">·</span>
                <span className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="inline-block h-[6px] w-[6px] rounded-full bg-[var(--color-purple,#8B5CF6)]"
                  />
                  <span data-testid="transcript-stat-tool-uses">
                    {transcriptStats.toolUses} tool uses
                  </span>
                </span>
                <span aria-hidden="true">·</span>
                <span className="inline-flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="inline-block h-[6px] w-[6px] rounded-full bg-[var(--color-warning,#D97706)]"
                  />
                  <span data-testid="transcript-stat-pending">
                    {transcriptStats.pending} pending
                  </span>
                </span>
              </div>
              <div className="min-h-0 flex-1">
                <BubbleTranscript content={transcript.content} task={task} />
              </div>
            </section>
          }
          right={
            <aside
              className="flex h-full min-h-0 flex-col border-l border-[var(--color-border,#e0dbd4)]"
              style={{ background: "var(--color-surface, #ffffff)" }}
              data-testid="task-detail-viewer"
            >
              <ViewerTabBar
                paths={selectedPaths}
                activePath={activePath}
                onActivate={setActivePath}
                onClose={handleCloseTab}
              />
              <div className="min-h-0 flex-1">
                <SmartViewer projectId={task.projectId} path={activePath} />
              </div>
            </aside>
          }
        />
      </div>
    </div>
  );
}
