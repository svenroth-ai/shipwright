# Making an interrupted iterate resumable from disk alone

## Context

An autonomous `/shipwright-iterate` session can be killed mid-phase by
context-window auto-compaction, and three gaps meant recovery from disk
alone was unreliable: (1) at `small` complexity a FEATURE run's mini-plan
existed only in conversational memory, never written to disk, so a killed
run lost its own plan; (2) the Step 8 review cascade's findings existed
only in a subagent's Task-tool return value until the orchestrator's next
action wrote them down — a compaction landing in that exact window lost
the finding outright; (3) `SKILL.md` §B1's resume replay-check trusted the
gitignored, runtime-only `session_handoff.md` and two weak markers, not the
per-run `reviews.json` record that is the actual source of truth for which
review types are still open. Full problem statement, six re-derived gaps,
and acceptance criteria: `.shipwright/planning/iterate/2026-08-09-compaction-state-audit.md`.

## Decision

Three independent fixes, one per gap: (1) the Mini-Plan Protocol's
persistence rule now applies at every complexity tier that runs it, with no
`small`-tier "inline in session only" carve-out; (2) an immediate-write
ordering mandate ("write the reviewer's raw reply to its payload file as
your very next action after it returns, before any other reasoning or the
next spawn") at every prose spawn site, backstopped by a code-level
`SubagentStop` salvage hook (`write-review-payload-on-stop.py`) for
`spec-reviewer`/`code-reviewer`/`doubt-reviewer` that independently salvages
a reviewer's raw reply from its own transcript if `reviews.json` doesn't
already show that type terminal; (3) `SKILL.md` §B1 now reads
`.shipwright/planning/iterate/{run_id}/reviews.json` directly via
`lib.review_record_core.read_record`/`pending_types`, gated on `self`
reaching a terminal status before any other pending type counts as an
interruption (a freshly-`init`'d record has every type pending before
anything is due — that is not evidence of interruption).

Internal Plan Review (opus-plan-reviewer, 11 findings), external plan
review (deepseek/openai, both `revise`), a dedicated architecture-mode call,
and the Step 8 internal + external code-review cascades all independently
converged on the same core shape and caught real, distinct issues at each
stage rather than fatiguing into rubber-stamps — full disposition tables
live in the iterate spec's `## Internal Plan Review`, `## External Plan
Review`, `## Architecture Review`, and `## External Code Review` sections.

## Consequences

Every consumer of `reviews.json` gains one more (the resume-progress
renderer in `handoff_iterate.py`), and the `SubagentStop` salvage hook adds
a new write surface (`{run_id}/{review_type}_salvaged_raw.json`) that a
resuming session must know to feed into
`record_review_pass.py record --payload-file` instead of losing the
finding to `close-missing`'s `not_run` default. The immediate-write mandate
is disclosed as a mitigation, not a closure: an agent can still ignore a
prose instruction, which is exactly why the code-level backstop exists
alongside it, not instead of it. A literal same-session kill-and-restart
could not be performed from inside the session doing the fix (Self-Review);
the mandated acceptance test instead drives two independent real
subprocesses — `record_review_pass.py show` and the real
`generate_handoff_on_stop.py` Stop-hook entrypoint — against a shared
fixture `reviews.json`, reading only from disk, no shared in-memory state.

## Rationale

Fixing all three gaps independently (rather than, say, a single unifying
"durability" abstraction) matches how they actually fail: each is a
different artifact (mini-plan file, review payload, resume signal) reaching
disk at a different point in the phase lifecycle, and each already had an
existing, working mechanism for the *other* complexity tiers or review
types — the fix in each case is closing a carve-out or wiring a read path
that already existed elsewhere in the same file, not inventing new
machinery. The code-level `SubagentStop` backstop specifically reuses this
repo's own existing precedent (`write-section-on-stop.py`, same
self-contained-no-`shared/scripts/lib`-import pattern for the same ADR-044
reason) rather than a novel hook design.

## Rejected alternatives

- **Give review subagents Write access** so they self-persist findings the
  instant they finish, closing the gap at the source. Rejected: it changes
  the security/capability surface of four subagent definitions deliberately
  restricted to `Read, Grep, Glob` (a review agent should not be able to
  write to the codebase it is reviewing), for a larger blast radius than
  this bug fix needs.
- **A `--mark-pending` pre-spawn write** to `reviews.json` before each
  reviewer spawn (external plan review, deepseek). Rejected as redundant:
  `record_review_pass.py init` already materializes all seven review types
  as `pending` up front, before any spawn — there is no "no entry at all"
  state once `init` has run; the actual gap was only that the doc didn't
  pin *when* `init` must run relative to Step 7, which is what got
  tightened instead.
- **Hardening the mini-plan `run_id` fallback's substring+mtime heuristic**
  against a same-description collision (external plan review, openai).
  Rejected as out of scope: it is the identical heuristic already used,
  unmodified, for the pre-existing `spec_path` candidate resolution three
  lines above it in the same function — hardening one call site and not its
  sibling would be inconsistent single-purpose gold-plating.
- **The dual-import (`try`/`except ImportError`) fallback pattern for
  `handoff_iterate.py`'s new `lib.review_record_core` import** (external
  code-review cascade, openai). Rejected after independent verification:
  that pattern exists in `review_record_schema.py` because its sibling
  import is loaded two different ways (package import and
  `importlib.util.spec_from_file_location`); `handoff_iterate.py` has no
  such second loading path — its only two consumers already do the
  `sys.path` setup a normal package import needs.
