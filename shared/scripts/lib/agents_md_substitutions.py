"""Canonical Codex-host substitution pairs for AGENTS.md's shared body.

One copy instead of three independent ones. Every consumer that needs to
derive AGENTS.md's expected shared-body content from CLAUDE.md's own content
imports these constants rather than re-declaring them:

- The greenfield instruction-driven step's own drift-guard test
  (``shared/tests/test_agents_md_greenfield_scaffolding.py``) — proves the
  prose in ``project-scaffolding.md`` is not stale relative to these pairs
  and to the real render function.
- The completion check that verifies a real project's AGENTS.md actually got
  the substitutions right, not merely that a marker string is present
  somewhere in the file (``shared/scripts/tools/verifiers/
  agents_md_completion_check.py`` — the executable backstop the required
  PR-review gate asked for twice, iterate-2026-09-23-m5-agents-md-generation-
  drift, R4).

Mirrors ``_render_claude_md``'s ``host_name`` branching in
``plugins/shipwright-adopt/scripts/lib/claude_md_renderer.py`` — not imported
directly (``shared/`` must not depend on a specific plugin, ADR-045). Kept in
sync by the greenfield drift-guard test above, which calls the real render
function with both host values and asserts these constants produce the same
fragments it does.

``project-scaffolding.md``'s own prose is necessarily a fourth, hand-written
copy of this same information (an LLM agent reads instructions, not code) —
that is the one copy nothing here can eliminate, and exactly what the
drift-guard test above exists to pin.
"""

from __future__ import annotations

#: "## Editing this file (keep it lean)" section's opening line.
DOC_TITLE_CLAUDE = "CLAUDE.md is **orientation + a terse invariant index**"
DOC_TITLE_CODEX = "AGENTS.md is **orientation + a terse invariant index**"

#: The standing-request section's host-naming sentence.
STANDING_REQUEST_CLAUDE = "Claude Code withholds subagent spawning until the user asks"
STANDING_REQUEST_CODEX = "Codex withholds subagent spawning until the user asks"

#: The growth-gate bullet — CLAUDE.md-only enforcement, replaced wholesale
#: rather than substring-edited (AGENTS.md has no such automated gate yet).
GROWTH_GATE_CLAUDE = (
    "- **Growth is gated:** iterate finalization flags a change that net-grows this\n"
    "  file by more than 30 lines (deliberate exception:\n"
    "  `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1`)."
)
GROWTH_GATE_CODEX = (
    "- **No automated growth gate for this file yet** — keep it lean by the\n"
    "  same restraint CLAUDE.md's line-cap enforces; watch it by hand."
)


def apply_codex_substitutions(claude_md_text: str) -> str:
    """Apply the three documented Codex-host substitutions to CLAUDE.md's
    text, returning the shared-body content AGENTS.md should carry before
    its Codex-only appendix. ``project-scaffolding.md`` states these are
    "the only host-specific content in the whole shared body" — everything
    else must survive unchanged, so callers comparing against this output
    should expect an exact match (after normalizing trailing whitespace).
    """
    return (
        claude_md_text
        .replace(STANDING_REQUEST_CLAUDE, STANDING_REQUEST_CODEX)
        .replace(DOC_TITLE_CLAUDE, DOC_TITLE_CODEX)
        .replace(GROWTH_GATE_CLAUDE, GROWTH_GATE_CODEX)
    )
