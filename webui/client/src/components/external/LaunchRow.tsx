import { Terminal, Copy, Laptop, Rocket } from "lucide-react";
import type { ExternalTask } from "../../lib/externalApi";

interface Props {
  task: ExternalTask;
  launching: boolean;
  onLaunch: (args: { resume: boolean }) => void;
  onFork: () => void;
  onClose: () => void;
}

/**
 * Launch row — three buttons always rendered; only "Copy command" is
 * active in variant-a. Terminal / VSCode are disabled with a clear reason
 * tooltip so users know this is a planned follow-up rather than a bug.
 */
export function LaunchRow({ task, launching, onLaunch, onFork, onClose }: Props) {
  const disabledAfterDone = task.state === "done";
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="launch-row">
      <button
        type="button"
        disabled={launching || disabledAfterDone}
        onClick={() => onLaunch({ resume: false })}
        className="inline-flex items-center gap-1.5 rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white shadow-sm hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="launch-copy-btn"
      >
        <Copy size={14} />
        {launching ? "Preparing…" : "Copy command"}
      </button>
      <button
        type="button"
        disabled={disabledAfterDone || task.state === "draft"}
        onClick={() => onLaunch({ resume: true })}
        className="inline-flex items-center gap-1.5 rounded border border-neutral-300 bg-white px-3 py-1 text-sm hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="launch-resume-btn"
        title="Re-emit the command with --resume so your Claude session picks up where it left off."
      >
        <Rocket size={14} />
        Resume
      </button>
      <button
        type="button"
        disabled={task.state === "draft"}
        onClick={onFork}
        className="inline-flex items-center gap-1.5 rounded border border-neutral-300 bg-white px-3 py-1 text-sm hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="launch-fork-btn"
        title="Create a sibling task derived from this one via --fork-session."
      >
        Fork
      </button>

      <div className="flex-1" />

      <button
        type="button"
        disabled
        className="inline-flex items-center gap-1.5 rounded border border-neutral-200 bg-neutral-50 px-3 py-1 text-sm text-neutral-400"
        title="Deferred to v2 (variant-a narrow): Terminal launcher ships after copy launcher is proven stable."
        data-testid="launch-terminal-btn"
      >
        <Terminal size={14} />
        Terminal (v2)
      </button>
      <button
        type="button"
        disabled
        className="inline-flex items-center gap-1.5 rounded border border-neutral-200 bg-neutral-50 px-3 py-1 text-sm text-neutral-400"
        title="Deferred to v2 (variant-a narrow): VSCode launcher ships after the Claude Code VSCode extension exposes --ide binding."
        data-testid="launch-vscode-btn"
      >
        <Laptop size={14} />
        VSCode (v2)
      </button>

      <button
        type="button"
        onClick={onClose}
        disabled={disabledAfterDone}
        className="inline-flex items-center gap-1.5 rounded border border-neutral-300 bg-white px-3 py-1 text-sm hover:bg-neutral-50 disabled:opacity-50"
        data-testid="close-task-btn"
      >
        Close task
      </button>
    </div>
  );
}
