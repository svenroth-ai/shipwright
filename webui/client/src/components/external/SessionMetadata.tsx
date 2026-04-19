import type { ExternalTask } from "../../lib/externalApi";

const STATE_STYLES: Record<ExternalTask["state"], string> = {
  draft: "bg-neutral-200 text-neutral-700",
  awaiting_external_start: "bg-amber-100 text-amber-900",
  active: "bg-green-100 text-green-900",
  idle: "bg-neutral-100 text-neutral-600",
  jsonl_missing: "bg-red-100 text-red-900",
  launch_failed: "bg-red-100 text-red-900",
  done: "bg-neutral-300 text-neutral-500",
};

interface Props {
  task: ExternalTask;
}

export function SessionMetadata({ task }: Props) {
  return (
    <div className="flex flex-col gap-1 rounded border border-neutral-200 bg-white p-3 text-sm" data-testid="session-metadata">
      <div className="flex items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-xs font-semibold ${STATE_STYLES[task.state]}`}
          data-testid="task-state-badge"
        >
          {task.state}
        </span>
        {task.parentTaskId && (
          <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs text-indigo-900" title="Forked from a parent task">
            forked
          </span>
        )}
      </div>
      <div>
        <span className="text-neutral-500">Session UUID: </span>
        <code className="font-mono text-xs">{task.sessionUuid}</code>
      </div>
      <div>
        <span className="text-neutral-500">Working dir: </span>
        <code className="font-mono text-xs">{task.cwd}</code>
      </div>
      {task.pluginDirs.length > 0 && (
        <div>
          <span className="text-neutral-500">Plugin dirs: </span>
          <span className="font-mono text-xs">{task.pluginDirs.length} passed</span>
        </div>
      )}
      {task.launchedAt && (
        <div>
          <span className="text-neutral-500">Launched: </span>
          <span className="text-xs">{new Date(task.launchedAt).toLocaleString()}</span>
        </div>
      )}
      {task.firstJsonlObservedAt && (
        <div>
          <span className="text-neutral-500">First JSONL: </span>
          <span className="text-xs">{new Date(task.firstJsonlObservedAt).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
