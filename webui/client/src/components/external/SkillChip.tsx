/*
 * SkillChip — 2026-04-23 iterate-20260423-chat-followups AC-3.
 *
 * Renders a compact, centered, grey pill for Claude Code skill-body
 * events. The session-parser detects the `Base directory for this skill:`
 * fingerprint + first `# <heading>` past the preamble and emits a
 * `skill-body` kind event whose `skillName` is extracted from that
 * heading. This component is the renderer.
 *
 * Visual language mirrors `SlashCommandChip` — grey pill, centered in the
 * transcript — with a `BookOpen` icon to differentiate from the
 * slash-command `↳` glyph.
 *
 * Collapse-only (no expansion): the full manual body is injected context
 * with no user-actionable content, so a chip is sufficient noise
 * reduction. Re-expansion (to see the full manual) is intentionally
 * deferred as future polish — if a user needs to debug what a skill
 * loaded, they can read the JSONL directly.
 *
 * Security: `skillName` renders as a React text node only. No
 * dangerouslySetInnerHTML, no derived className interpolation.
 */

import { BookOpen } from "lucide-react";

interface Props {
  skillName: string;
}

export function SkillChip({ skillName }: Props) {
  return (
    <div className="flex justify-center my-2" data-testid="skill-chip">
      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-mono text-[11px]"
        style={{
          background: "rgba(107,114,128,0.10)",
          color: "var(--color-muted, #6b7280)",
        }}
      >
        <BookOpen size={11} aria-hidden="true" style={{ opacity: 0.75 }} />
        <span style={{ opacity: 0.75 }}>Skill:</span>
        <span
          style={{ color: "var(--color-text, #1a1a1a)", fontWeight: 500 }}
          data-testid="skill-chip-name"
        >
          {skillName}
        </span>
      </span>
    </div>
  );
}
