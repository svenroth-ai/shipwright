/*
 * Single shared launch CTA for external-launch tasks.
 *
 * 2.1 introduces this component with the `primary` variant only (placed
 * in the TaskDetail header). 2.3 adds `compact` (TaskBoard cards) and
 * `inline` (Inbox rows). Each variant emits the same command string for
 * a given task — only the click semantics differ:
 *
 *   primary  — full-size button: copy + show "Copied" + announce.
 *   compact  — icon-only with tooltip: copy.
 *   inline   — link-style: navigate to TaskDetail (then user copies there).
 *
 * Platform detection is browser-side: PowerShell on Windows, POSIX
 * elsewhere. Single button per platform — the cmd.exe variant from the
 * sub-iterate 1 CopyCommandCard is intentionally not surfaced here
 * (Early Access target audience runs PowerShell).
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, Terminal as TerminalIcon } from "lucide-react";

import type { CopyCommandForms, ExternalTask } from "../../lib/externalApi";
import { useLaunchTask } from "../../hooks/useLaunchTask";

export type TerminalLaunchVariant = "primary" | "compact" | "inline";

interface Props {
  task: ExternalTask;
  variant?: TerminalLaunchVariant;
  /** Override platform detection (used in tests + Storybook). */
  platform?: "windows" | "posix";
  /** Resume vs. fresh-start. Defaults to true once the task has launched once. */
  resume?: boolean;
}

export function TerminalLaunchButton({
  task,
  variant = "primary",
  platform,
  resume,
}: Props) {
  const navigate = useNavigate();
  const launchMut = useLaunchTask();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const detectedPlatform = platform ?? detectPlatform();
  const wantResume = resume ?? task.state !== "draft";

  const copy = useCallback(async () => {
    setError(null);
    try {
      const result = await launchMut.mutateAsync({ taskId: task.taskId, resume: wantResume });
      const command = pickCommand(result.commands, detectedPlatform);
      await writeClipboard(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [launchMut, task.taskId, wantResume, detectedPlatform]);

  if (variant === "inline") {
    return (
      <button
        type="button"
        onClick={() => navigate(`/tasks/${task.taskId}`)}
        className="inline-flex items-center gap-1 text-xs text-blue-700 hover:underline"
        data-testid="terminal-launch-inline"
      >
        <TerminalIcon size={12} /> Open task
      </button>
    );
  }

  if (variant === "compact") {
    return (
      <button
        type="button"
        onClick={() => void copy()}
        disabled={launchMut.isPending}
        className="rounded p-1 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 disabled:opacity-50"
        title={copied ? "Copied!" : "Copy launch command"}
        aria-label="Copy launch command"
        data-testid="terminal-launch-compact"
      >
        <TerminalIcon size={14} />
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-1" data-testid="terminal-launch-primary">
      <button
        type="button"
        onClick={() => void copy()}
        disabled={launchMut.isPending}
        className="inline-flex items-center gap-2 rounded bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="terminal-launch-btn"
        aria-label={copied ? "Launch command copied" : "Copy launch command for terminal"}
      >
        <Copy size={14} />
        {launchMut.isPending ? "Preparing…" : copied ? "Copied — paste into terminal" : "Copy launch command"}
      </button>
      <span className="text-xs text-neutral-500" data-testid="terminal-launch-platform">
        {detectedPlatform === "windows" ? "PowerShell" : "POSIX shell (bash/zsh)"}
      </span>
      {error && (
        <span className="text-xs text-red-700" data-testid="terminal-launch-error">
          {error}
        </span>
      )}
    </div>
  );
}

function detectPlatform(): "windows" | "posix" {
  if (typeof navigator === "undefined") return "posix";
  return /windows/i.test(navigator.userAgent) ? "windows" : "posix";
}

function pickCommand(commands: CopyCommandForms, platform: "windows" | "posix"): string {
  return platform === "windows" ? commands.powershell : commands.posix;
}

async function writeClipboard(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // Hard fallback: textarea + execCommand. Modern browsers prefer the
  // Clipboard API, but Firefox/Safari without HTTPS fall back to this.
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}
