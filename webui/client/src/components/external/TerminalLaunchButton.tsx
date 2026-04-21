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
  /**
   * Compact-variant affordance (iterate 3.7c-1): show a short text label next
   * to the icon so the control is self-describing on a kanban card. Ignored
   * for `primary` (always labeled) and `inline` (link style).
   */
  showLabel?: boolean;
}

export function TerminalLaunchButton({
  task,
  variant = "primary",
  platform,
  resume,
  showLabel = false,
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
    const label = wantResume ? "Resume" : "Launch";
    return (
      <button
        type="button"
        onClick={(ev) => {
          // Don't let the click bubble to a parent card click-handler.
          ev.stopPropagation();
          void copy();
        }}
        disabled={launchMut.isPending}
        className={
          "inline-flex items-center gap-1 px-1.5 py-0.5 text-[11px] font-medium " +
          "text-[var(--color-muted)] transition-colors hover:bg-[var(--color-muted-bg)] hover:text-[var(--color-text)] disabled:opacity-50"
        }
        style={{ borderRadius: "var(--radius-button)" }}
        title={copied ? "Copied!" : `${label} command`}
        aria-label={`${label} command`}
        data-testid="terminal-launch-compact"
      >
        <TerminalIcon size={12} />
        {showLabel && (
          <span className="leading-none">{copied ? "Copied" : label}</span>
        )}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-1" data-testid="terminal-launch-primary">
      <button
        type="button"
        onClick={() => void copy()}
        disabled={launchMut.isPending}
        className="inline-flex items-center gap-2 bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
        style={{ borderRadius: "var(--radius-button)" }}
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
