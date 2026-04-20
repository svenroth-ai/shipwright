/*
 * TaskDetailPage — thin composition shell for the 3-pane task detail
 * surface (iterate 3 section 04, AD-03.06 + FR-03.30..36).
 *
 * The old vertical stack (LaunchRow + CopyCommandCard + SessionMetadata
 * + TranscriptViewer) is gone: LaunchRow and CopyCommandCard are
 * DELETED from the codebase (plan § 7 O15), SessionMetadata moves into
 * the header's 3-dots menu as a debug footer, and the transcript is
 * now the center pane of TaskDetailThreePane.
 *
 * Regression guards survive every edit:
 *   - No chat composer (DO-NOT #3). Only interactive affordances are
 *     the header CTA, project chip, 3-dots menu, splitter handles, and
 *     folder-tree rows.
 *   - No webui-initiated `claude --resume` (DO-NOT #5). The resume CTA
 *     COPIES TO CLIPBOARD.
 */

import { useState } from "react";
import { useParams } from "react-router-dom";

import { useExternalTask } from "../hooks/useExternalTasks";
import { useTaskTranscript } from "../hooks/useTaskTranscript";
import { BubbleTranscript } from "../components/external/BubbleTranscript";
import { TaskDetailHeader } from "../components/external/TaskDetailHeader";
import { TaskDetailThreePane } from "../components/external/TaskDetailThreePane";
import { FolderTree } from "../components/external/FolderTree";
import { SmartViewer } from "../components/external/SmartViewer";

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, error } = useExternalTask(taskId);
  const transcript = useTaskTranscript(taskId ?? null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  if (error) {
    return (
      <div className="p-4 text-sm text-red-700" data-testid="task-detail-error">
        Error loading task: {String(error)}
      </div>
    );
  }
  if (!task) {
    return (
      <div className="p-4 text-sm text-neutral-500" data-testid="task-detail-loading">
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
              selectedPath={selectedPath}
              onSelect={setSelectedPath}
            />
          }
          center={
            <section
              className="flex h-full min-h-0 flex-col"
              style={{ background: "var(--color-bg, #f5f0eb)" }}
              data-testid="task-detail-transcript"
            >
              <div
                className="flex items-center justify-between border-b border-[var(--color-border,#e0dbd4)] px-4 py-1.5 text-[11px]"
                style={{ background: "var(--color-surface, #ffffff)", color: "var(--color-muted, #6b7280)" }}
              >
                <span>Transcript</span>
                <span>
                  status:{" "}
                  <span data-testid="transcript-status">{transcript.status}</span>
                  {transcript.fingerprint && ` · fp ${transcript.fingerprint}`}
                  {` · ${transcript.size} B`}
                </span>
              </div>
              <div className="min-h-0 flex-1">
                <BubbleTranscript content={transcript.content} />
              </div>
            </section>
          }
          right={
            <aside
              className="flex h-full min-h-0 flex-col border-l border-[var(--color-border,#e0dbd4)]"
              style={{ background: "var(--color-surface, #ffffff)" }}
              data-testid="task-detail-viewer"
            >
              <div
                className="flex items-center gap-2 border-b border-[var(--color-border,#e0dbd4)] px-4 py-2 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--color-muted, #6b7280)", background: "var(--color-bg, #f5f0eb)" }}
              >
                <span className="flex-1 truncate">{selectedPath ?? "Viewer"}</span>
              </div>
              <div className="min-h-0 flex-1">
                <SmartViewer projectId={task.projectId} path={selectedPath} />
              </div>
            </aside>
          }
        />
      </div>
    </div>
  );
}
