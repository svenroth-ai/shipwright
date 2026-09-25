# AGENTS.md generation for Codex CLI, single-sourced with CLAUDE.md

- **Status:** accepted
- **Date:** 2026-09-24

## Context

Codex CLI reads `AGENTS.md` as its own, native, first-class convention — not
as a fallback for a missing `CLAUDE.md`. Neither `/shipwright-adopt`
(brownfield) nor `/shipwright-project` (greenfield) ever wrote one, so a
Codex session in any Shipwright-managed project got zero Shipwright guidance,
regardless of whether `CLAUDE.md` existed. Separately, this monorepo's own
root `AGENTS.md` had drifted: it hardcoded two Codex model-slug/reasoning-
effort DEFAULT-PRESCRIBING bullets that belong to `codex_review_model_resolution.py`'s
dynamic resolution, not a static file.

## Decision

Generate `AGENTS.md` from the exact same render function CLAUDE.md's own
writer calls (`_render_claude_md(..., host_name=...)`), never a second
template or a second hand-maintained f-string. `host_name` parameterizes the
two spots in the shared body that name the host (the standing-request
section's sentence, and the "Editing this file" section's opening line +
growth-gate bullet); every other line is identical. A small, separately
maintained Codex-only appendix (`shared/templates/codex-agents-md-appendix.md`)
is appended by both producers at generation time, carrying an inert
HTML-comment idempotency marker (`<!-- shipwright:codex-agents-md-appendix -->`)
as its own first line — decoupled from its visible heading, so neither a
future reword of the heading nor a project's own pre-existing, unrelated
section sharing that heading text can cause a false "already delivered".
Adopt's existing load-bearing-preservation policy for `CLAUDE.md` (>1KB
existing file preserved untouched, suggestion written to a side-file, both
the standing-request section and the Codex appendix appended idempotently)
is reused unchanged for `AGENTS.md`, keyed by an explicit filename parameter
already threaded through `preserve_existing.py`'s helpers. Greenfield writes
both files unconditionally for every Full Application scope project, never
gated on an interview answer; `project-scaffolding.md`'s instructions name
the two literal substitutions needed (host-name sentence; editing/growth-gate
bullet) since the LLM agent reuses the CLAUDE.md content it just filled
rather than re-rendering. The root `AGENTS.md`/`CLAUDE.md` drift-fix removes
the two hardcoded model-slug/reasoning-effort bullets, leaving the
pre-existing xhigh/max cautionary line untouched.

## Consequences

Every newly adopted or newly scaffolded Full-Application project now ships
an `AGENTS.md`, so a Codex-driven session gets the same iterate-workflow,
review-cascade, and plain-language rules a Claude Code session already gets
from `CLAUDE.md`. `SKILL.md` and its `step-7-scaffolding.md` /
`step-8-completion.md` references were updated to name `AGENTS.md` alongside
`CLAUDE.md` in every checkpoint/verification/banner, closing a gap where an
agent following only those summary surfaces would never reach
`project-scaffolding.md`'s AGENTS.md step (doubt-reviewer, high). The
greenfield single-source guarantee is NOT code-enforced the way the
brownfield path is — an LLM performs two manual substitutions inside filled
prose rather than calling the shared render function — accepted as an
inherent property of instruction-driven generation, the same shape CLAUDE.md's
own greenfield path already has; a new test
(`test_greenfield_agents_md_substitution_instructions_match_the_render_path`)
mechanically proves the instructed substitution text is not stale relative to
the render path. The Codex appendix's idempotency marker shares the same
plain-heading-match risk class as the pre-existing standing-request marker
(a marker-stripped hand-copy of the rendered text could still duplicate on a
later adopt run) — accepted, not newly introduced by this change.

## Rejected alternatives

- **Independent `AGENTS.md` template/render path per producer, pinned against
  CLAUDE.md's content by a drift test** (architecture-review Option B) —
  rejected: reintroduces exactly the split-brain shape that already caused a
  real, shipped drift bug for CLAUDE.md's own two producers
  (`test_claude_md_template.py`'s own docstring), just for a second file.
- **Do nothing** (architecture-review Option C) — rejected: a Codex session
  in any Shipwright-managed project continues to receive zero Shipwright
  guidance.
- **Deriving the visible heading as the idempotency signal** (original
  design) — rejected after doubt-review + external review both independently
  flagged the same failure mode from different angles (heading-reword
  desync; natural collision with a project's own pre-existing section of the
  same generic name) — replaced with the inert HTML-comment marker embedded
  in the appendix file itself.
- **Content-hash secondary idempotency check** (doubt-review suggestion) —
  rejected: would defeat the marker design's actual purpose of surviving a
  legitimate appendix reword between adopt runs, for a narrow edge case
  (marker-stripped hand-copy) already shared with the pre-existing
  standing-request marker.
