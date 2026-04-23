/*
 * ToolCard — 2026-04-23 iterate-20260423-chat-rendering-polish AC-1 + AC-2.
 *
 * Collapsed-by-default tool_use card matching mockup bubble-states.html
 * §Tool use. Header shows icon + tool name + chevron. Click header to
 * toggle the body, which displays the tool_use input as JSON (or the
 * raw string if input is a string). Expansion state is LOCAL to the
 * card (useState) — keyed by the component instance, which React
 * preserves across parent re-renders because the caller passes a stable
 * `key={toolUseId}`.
 *
 * Generic by design: any tool name (Read, Edit, Bash, TaskCreate,
 * custom MCP tool, etc.) gets the same card shape — no silent drops.
 * Icon-per-tool differentiation (Read=blue, Bash=green, etc. per mockup)
 * is a future polish; this iterate just fixes the "tool cards eat too
 * much vertical space" bug by making them collapsed by default.
 *
 * Security: `name` and `input` render as React text nodes only. JSON
 * stringification of `input` is bounded by JSON.stringify (standard
 * escaping) and shown inside a <pre> element with no HTML parsing.
 */

import { useState } from "react";
import { ChevronRight, Wrench } from "lucide-react";

import { ToolOutputBlock } from "./ToolOutputBlock";

interface Props {
  id: string;
  name: string;
  input: unknown;
  /**
   * 2026-04-23 — iterate-20260423-chat-followups AC-1.
   * Tool output folded into the same card via `tool_use_id` correlation.
   * When absent, the expanded card shows only the input (old behavior).
   * When present, the expanded card shows input AND output, eliminating
   * the separate tool_result bubble that used to render next to its
   * tool_use.
   */
  result?: { content: string; is_error: boolean };
}

function formatInput(input: unknown): string {
  if (input == null) return "";
  if (typeof input === "string") return input;
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

export function ToolCard({ id, name, input, result }: Props) {
  const [expanded, setExpanded] = useState(false);
  const body = formatInput(input);
  const hasInput = body.trim().length > 0;
  const hasOutput = result != null;

  return (
    <div
      className="overflow-hidden"
      style={{
        background: "var(--color-surface, #ffffff)",
        border: "1px solid var(--color-border, #e0dbd4)",
        borderRadius: "var(--radius-button, 8px)",
        boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
      }}
      data-testid="tool-card"
      data-tool-use-id={id}
      data-expanded={expanded ? "true" : "false"}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2 text-left"
        style={{ minHeight: 38, background: "transparent" }}
        data-testid="tool-card-header"
        aria-expanded={expanded}
      >
        <div
          className="flex items-center justify-center rounded-md shrink-0"
          style={{
            width: 22,
            height: 22,
            background: "var(--color-muted-bg, #ede8e1)",
            color: "var(--color-accent, #857568)",
          }}
        >
          <Wrench size={12} aria-hidden="true" />
        </div>
        <span
          className="flex-1 min-w-0 font-mono text-[12.5px] truncate"
          style={{ color: "var(--color-text, #1a1a1a)", fontWeight: 500 }}
          data-testid="tool-card-title"
        >
          {name}
        </span>
        <ChevronRight
          size={14}
          className="shrink-0"
          style={{
            color: "var(--color-muted, #6b7280)",
            transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
          aria-hidden="true"
        />
      </button>
      {expanded && hasInput && (
        <div
          className="px-3.5 py-2.5"
          style={{
            borderTop: "1px solid var(--color-border, #e0dbd4)",
            background: "#fafaf8",
            fontFamily: "var(--font-mono, ui-monospace, Menlo, Consolas, monospace)",
            fontSize: 12,
            lineHeight: 1.6,
          }}
          data-testid="tool-card-body"
        >
          <pre
            className="overflow-x-auto whitespace-pre-wrap break-words"
            style={{ color: "var(--color-text, #1a1a1a)", margin: 0 }}
          >
            {body}
          </pre>
        </div>
      )}
      {expanded && hasOutput && (
        <div
          className="px-3.5 py-2.5"
          style={{
            borderTop: "1px solid var(--color-border, #e0dbd4)",
            background: "#fafaf8",
          }}
          data-testid="tool-card-output"
        >
          <ToolOutputBlock text={result.content} isError={result.is_error} />
        </div>
      )}
    </div>
  );
}
