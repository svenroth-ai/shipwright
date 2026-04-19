/*
 * Task Detail — LaunchRow + CopyCommandCard + SessionMetadata +
 * TranscriptViewer. Plan D'' variant-a TaskDetail.
 *
 * REPLACED: the previous chat-panel implementation (pre-iterate 14.x
 * chat engine, assistant-ui + ndjson-parser). That path is deleted in
 * Sub-iterate 3. This page is the single surface for an external-launch
 * task in the new architecture.
 */

import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import type { CopyCommandForms } from "../lib/externalApi";
import { useExternalTask, useCloseExternalTask } from "../hooks/useExternalTasks";
import { useForkTask, useLaunchTask } from "../hooks/useLaunchTask";
import { useTaskTranscript } from "../hooks/useTaskTranscript";

import { LaunchRow } from "../components/external/LaunchRow";
import { CopyCommandCard } from "../components/external/CopyCommandCard";
import { SessionMetadata } from "../components/external/SessionMetadata";
import { TranscriptViewer } from "../components/external/TranscriptViewer";
import { TerminalLaunchButton } from "../components/external/TerminalLaunchButton";
import { EditableTaskTitle } from "../components/external/EditableTaskTitle";

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, error } = useExternalTask(taskId);
  const launchMut = useLaunchTask();
  const forkMut = useForkTask();
  const closeMut = useCloseExternalTask();
  const transcript = useTaskTranscript(taskId ?? null);

  const [commands, setCommands] = useState<CopyCommandForms | null>(null);

  const handleLaunch = useCallback(
    async ({ resume }: { resume: boolean }) => {
      if (!taskId) return;
      const result = await launchMut.mutateAsync({ taskId, resume });
      setCommands(result.commands);
    },
    [taskId, launchMut],
  );

  const handleFork = useCallback(async () => {
    if (!taskId || !task) return;
    const result = await forkMut.mutateAsync({ taskId, title: `${task.title} — fork` });
    setCommands(result.commands);
  }, [taskId, task, forkMut]);

  const handleClose = useCallback(() => {
    if (!taskId) return;
    closeMut.mutate(taskId);
  }, [taskId, closeMut]);

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
    <div className="flex h-full flex-col gap-4 p-4" data-testid="task-detail-page">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-neutral-500 hover:text-neutral-900" aria-label="Back to board">
            <ArrowLeft size={16} />
          </Link>
          <EditableTaskTitle task={task} />
        </div>
        <TerminalLaunchButton task={task} variant="primary" />
      </header>

      <LaunchRow
        task={task}
        launching={launchMut.isPending || forkMut.isPending}
        onLaunch={(args) => void handleLaunch(args)}
        onFork={() => void handleFork()}
        onClose={handleClose}
      />

      {commands && <CopyCommandCard commands={commands} />}

      <SessionMetadata task={task} />

      <section className="flex flex-col gap-2 rounded border border-neutral-200 bg-white p-3">
        <div className="flex items-center justify-between text-xs text-neutral-500">
          <span>Transcript</span>
          <span>
            status: <span data-testid="transcript-status">{transcript.status}</span>
            {transcript.fingerprint && ` · fp ${transcript.fingerprint}`}
            {` · ${transcript.size} B`}
          </span>
        </div>
        <TranscriptViewer content={transcript.content} />
      </section>
    </div>
  );
}
