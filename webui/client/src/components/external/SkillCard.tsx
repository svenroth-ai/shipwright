/*
 * SkillCard — 2026-04-23 iterate-20260423-chat-livetest-2 AC-A / ADR-056.
 *
 * Collapsed-by-default card for Claude Code skill-loader events. Header
 * shows `BookOpen` icon + `Skill: <name>` + chevron. Click header to
 * expand and reveal the skill manual rendered as Markdown via the
 * project's existing `MarkdownText` pipeline (react-markdown + remark-gfm
 * + rehype-highlight, XSS-safe default).
 *
 * Replaces `<SkillChip>` (ADR-055) — the chip was too aggressive at
 * hiding the manual; user live-test 2026-04-23 surfaced the need to be
 * able to expand the manual on demand. User picked "Option C" during
 * the iterate interview: compact chip-header + expand-to-Markdown body.
 *
 * Expansion state is LOCAL to the card instance (`useState`). React
 * preserves the component instance across parent re-renders when the
 * key is stable (keyed by `event.uuid` at the transcript level) so
 * poll-driven transcript refreshes don't reset the expanded state.
 *
 * Security: `skillName` and `body` are user-originated text from the
 * CLI's skill manual. `skillName` renders as a React text node only.
 * `body` flows through `MarkdownText` which uses the default
 * `react-markdown` sanitizer (no raw HTML pass-through).
 */

import { useState } from "react";
import { BookOpen, ChevronRight } from "lucide-react";

import { MarkdownText } from "./MarkdownText";

interface Props {
  skillName: string;
  /** Markdown body from the H1 onward (optional — legacy parsed events). */
  body?: string;
}

export function SkillCard({ skillName, body }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasBody = typeof body === "string" && body.trim().length > 0;

  return (
    <div className="flex justify-start" data-testid="skill-card">
      <div
        className="max-w-[90%] w-full overflow-hidden"
        style={{
          background: "var(--color-surface, #ffffff)",
          border: "1px solid var(--color-border, #e0dbd4)",
          borderRadius: "var(--radius-button, 8px)",
          boxShadow: "0 1px 4px rgba(0,0,0,0.05)",
        }}
        data-expanded={expanded ? "true" : "false"}
      >
        <button
          type="button"
          onClick={() => hasBody && setExpanded((v) => !v)}
          className="w-full flex items-center gap-2.5 px-3.5 py-2 text-left"
          style={{
            minHeight: 38,
            background: "transparent",
            cursor: hasBody ? "pointer" : "default",
          }}
          data-testid="skill-card-header"
          aria-expanded={expanded}
          disabled={!hasBody}
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
            <BookOpen size={12} aria-hidden="true" />
          </div>
          <span
            className="shrink-0 text-[11px] uppercase tracking-wide"
            style={{ color: "var(--color-muted, #6b7280)", fontWeight: 600 }}
          >
            Skill
          </span>
          <span
            className="flex-1 min-w-0 font-mono text-[12.5px] truncate"
            style={{ color: "var(--color-text, #1a1a1a)", fontWeight: 500 }}
            data-testid="skill-card-name"
          >
            {skillName}
          </span>
          {hasBody && (
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
          )}
        </button>
        {expanded && hasBody && (
          <div
            className="px-3.5 py-2.5"
            style={{
              borderTop: "1px solid var(--color-border, #e0dbd4)",
              background: "#fafaf8",
            }}
            data-testid="skill-card-body"
          >
            <MarkdownText text={body!} />
          </div>
        )}
      </div>
    </div>
  );
}
