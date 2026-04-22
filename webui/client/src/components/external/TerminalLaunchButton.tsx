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
 *   solid    — 3.7d-b1: always-visible brown-solid button (label + icon,
 *              13px / 600 weight). Used on TaskCard for Launch + Resume
 *              CTAs and anywhere else we want a primary action inline.
 *
 * Iterate 3.7e-a (Foundation, 2026-04-22) — R3 button variants:
 *   - `solid` variant now accepts an optional `color` prop:
 *       "brown" (default — var(--color-primary)) — Resume actions.
 *       "green" (var(--color-success))           — Launch actions on draft
 *                                                  / awaiting_external_start
 *                                                  cards (Backlog column).
 *   - `size="xs"` option: 12px text / 500 weight / 4px 10px padding / 14px
 *     icon — the finer TaskCard button size per plan R3.
 *   - Terminal icon stays LEFT of the label (already the case).
 *   - Testids updated to encode color for b1 Playwright assertions:
 *       terminal-launch-solid-launch-green (new)
 *       terminal-launch-solid-resume-brown (new)
 *       terminal-launch-solid-launch / -resume (back-compat testid kept
 *         as the same element for existing tests).
 *
 * Platform detection is browser-side: PowerShell on Windows, POSIX
 * elsewhere. Single button per platform — the cmd.exe variant from the
 * sub-iterate 1 CopyCommandCard is intentionally not surfaced here
 * (Early Access target audience runs PowerShell).
 */

import type React from "react";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, Terminal as TerminalIcon } from "lucide-react";

import type { CopyCommandForms, ExternalTask } from "../../lib/externalApi";
import { useLaunchTask } from "../../hooks/useLaunchTask";

export type TerminalLaunchVariant = "primary" | "compact" | "inline" | "solid";
export type TerminalLaunchColor = "brown" | "green" | "orange";
export type TerminalLaunchSize = "md" | "xs";

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
  /**
   * Solid-variant color (iterate 3.7e-a R3). "brown" (default) = Resume /
   * generic primary; "green" = Launch (Backlog-only per plan). Ignored for
   * non-solid variants.
   */
  color?: TerminalLaunchColor;
  /**
   * Solid-variant size (iterate 3.7e-a R3). "md" (default) keeps the existing
   * 13px / 600 weight button. "xs" renders the finer TaskCard button — 12px
   * text, 500 weight, 4px 10px padding, 14px icon. Ignored for non-solid
   * variants.
   */
  size?: TerminalLaunchSize;
  /**
   * Solid-variant label override (iterate 3.7f). Defaults to "Launch" /
   * "Resume" based on `wantResume`. Sven UAT 2026-04-22: `active` state wants
   * "Terminal" (copy the same resume command but the label reflects that
   * Claude is already running and we're just jumping into the terminal).
   * `idle` keeps "Resume" (session exists but process ended → real resume).
   * Inbox + Ask bubble use "Answer" with the same clipboard handler.
   */
  label?: string;
}

export function TerminalLaunchButton({
  task,
  variant = "primary",
  platform,
  resume,
  showLabel = false,
  color = "brown",
  size = "md",
  label,
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

  if (variant === "solid") {
    // Solid primary action. Used on TaskCards (Launch + Resume pair
    // always-visible). Self-describing: the label always includes the
    // mode, and a transient "Copied" state swaps in for 1.5s after click.
    //
    // Iterate 3.7e-a R3:
    //   color="brown"  → var(--color-primary) — Resume actions (default).
    //   color="green"  → var(--color-success) — Launch actions in Backlog.
    //   size="md"      → 13px / 600 weight / 3 × 5px padding (existing).
    //   size="xs"      → 12px / 500 weight / 4 × 10px padding (finer
    //                    TaskCard button per plan R3).
    // The Terminal icon is always rendered LEFT of the label.
    const effectiveLabel = label ?? (wantResume ? "Resume" : "Launch");
    const isGreen = color === "green";
    const isOrange = color === "orange";
    const isXs = size === "xs";
    // iterate 3.7g: orange = Resume (fine warm terracotta, not alert), green
    // = Launch (Backlog-only), brown = Terminal (default).
    const bgVar = isGreen
      ? "var(--color-success)"
      : isOrange
        ? "var(--color-resume)"
        : "var(--color-primary)";
    const hoverBg = isGreen
      ? "#047857"
      : isOrange
        ? "var(--color-resume-hover)"
        : "var(--color-primary-hover)";
    const ringVar = isGreen
      ? "var(--color-success)"
      : isOrange
        ? "var(--color-resume)"
        : "var(--color-primary)";
    const iconSize = isXs ? 14 : 13;
    return (
      <button
        type="button"
        onClick={(ev) => {
          ev.stopPropagation();
          void copy();
        }}
        disabled={launchMut.isPending}
        className={
          "inline-flex items-center justify-center gap-1.5 " +
          "font-semibold text-white transition-colors " +
          "disabled:cursor-not-allowed disabled:opacity-60 " +
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--color-surface)]"
        }
        style={{
          borderRadius: "var(--radius-button)",
          background: bgVar,
          padding: isXs ? "4px 10px" : "5px 12px",
          fontSize: isXs ? "12px" : "13px",
          fontWeight: isXs ? 500 : 600,
          // Custom CSS var used by Tailwind's focus-visible:ring classes.
          ["--tw-ring-color" as string]: ringVar,
        } as React.CSSProperties}
        onMouseEnter={(ev) => {
          ev.currentTarget.style.background = hoverBg;
        }}
        onMouseLeave={(ev) => {
          ev.currentTarget.style.background = bgVar;
        }}
        title={copied ? "Copied!" : `Copy ${effectiveLabel} command`}
        aria-label={`${effectiveLabel} command`}
        data-testid={`terminal-launch-solid-${wantResume ? "resume" : "launch"}`}
        data-color={color}
        data-size={size}
        data-label={effectiveLabel}
      >
        <TerminalIcon size={iconSize} />
        <span className="leading-none">{copied ? "Copied" : effectiveLabel}</span>
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
