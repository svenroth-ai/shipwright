# ADR-129: Bloat exception — `plugins/shipwright-iterate/agents/sub-iterate-runner.md` raised to 500-LOC

<!-- Grants a bloat-baseline exception for the three-line growth caused by
     iterate-2026-09-03-review-scratch-path's round-9 external-review fix.
     Referenced from shipwright_bloat_baseline.json (state="exception",
     adr="ADR-129"). Does NOT supersede ADR-119: that ADR already carries the
     Ousterhout/YAGNI/Chesterton-Fence argument this one reuses; ADR-129 only
     records the incremental bump, exactly the pattern ADR-125 used for
     `iterate_checks.py`. -->

- **Status:** accepted
- **Date:** 2026-09-04
- **Re-Review-Date:** 2026-10-31 _(co-scheduled with ADR-119's own re-review —
  the same review deciding whether the finalization list can be derived
  from SKILL.md instead of restated should fold this bump into that
  decision)_
- **Incident Reference:** iterate-2026-09-03-review-scratch-path, PR #676
  round-9 external review (Tier-3, `openai/gpt-5.6-luna`). Round 8 replaced
  `--run-id "{run_id}"` textual interpolation with a `RUN_ID="{run_id}"`
  assignment reused as `"$RUN_ID"` at every downstream site — closing every
  *reuse* site but leaving the assignment itself as one remaining
  interpolation point (a value containing a `'` or `$(...)` can still break
  a plain quoted assignment's own parsing). Round 9 correctly caught this.

## Context

`sub-iterate-runner.md` was already an ADR-119 exception at `current: 497`.
Step 2's external-review-cascade block assigns `RUN_ID` from the templated
`{run_id}` placeholder and reuses it in a `trap ... EXIT` and two
`review_scratch.py` calls. Closing the round-9 injection finding requires
reading `{run_id}` through a quoted heredoc (`RUN_ID="$(cat <<'EOF' ...
EOF
)"`) instead of a plain assignment — a quoted heredoc terminator disables
ALL shell expansion inside it, so the value lands in `$RUN_ID` as pure
literal data no matter what it contains, closing the gap a plain assignment
cannot. That costs **+3 lines** (497 → 500): the one-line assignment becomes
a four-line heredoc.

## Ousterhout Argument

Unchanged from ADR-119, restated because it applies verbatim: this is a
**runtime prompt** — the only text guaranteed to be loaded before the
subagent executes Step 2. The heredoc is not an internal that could be
encapsulated behind a pointer; it is the exact command text the agent must
emit verbatim to close the injection path, and a subagent that never
follows a "see reference X for the safe form" pointer would silently keep
using the unsafe plain assignment. The three added lines are exactly the
minimum shell syntax a quoted heredoc requires (opening line, body line,
delimiter line) — there is no narrower expression of "read this value
without letting the shell parse it."

## YAGNI Check

The three added lines have no speculative content: they are the fixed,
minimal syntax of a `cat <<'EOF' ... EOF` heredoc assignment, used exactly
once, closing exactly the injection path round 9 identified. Nothing here
is scope carried "for later."

## Chesterton-Fence Check

ADR-119's fences (the byte-identical-pinned Bloat Checklist section, the
prior test-only split, the torn-down F2 label collision) are all unchanged
by this edit — Step 2's cascade block is untouched territory relative to
those decisions. No new fence is being erected or removed here.

## Decision

Raise `current` for `plugins/shipwright-iterate/agents/sub-iterate-runner.md`
from **497 to 500**, `state: "exception"`, `adr: "ADR-129"`, in the same
commit as the change that crosses it. Re-review folds into ADR-119's
2026-10-31 date.

## Consequences

Any future PR touching this file is now measured against 500, not 497. The
next check registered here will need its own (or a renewed) exception
unless the ADR-119 re-review has landed the SKILL.md-derivation loader by
then, at which point the duplicated finalization-phase list — and likely
this cascade block too — would be generated rather than hand-maintained.

## Rejected alternatives

- **Shrink the file by 3 lines elsewhere to stay net-neutral:** considered
  first. Rejected for the same reason ADR-125 rejected it: the surrounding
  content (Step 1 setup, Step 3.4 risk re-check, Step 3.5/3.7/3.8 review
  gates, Step 4's finalization-phase enumeration) is either load-bearing
  incident-derived documentation ADR-119 already justified line-by-line, or
  would read as gaming the counter rather than a genuine improvement.
- **Keep the plain `RUN_ID="{run_id}"` assignment and rely on
  `review_scratch.py`'s own charset validation downstream:** this is
  exactly what round 9 rejected — the shell parses and can execute
  metacharacters in the assignment's right-hand side BEFORE
  `review_scratch.py` ever runs, so downstream validation is too late to
  prevent the injection itself.
- **Use single-quoting (`RUN_ID='{run_id}'`) instead of a heredoc:** weaker,
  not equivalent — a value containing an embedded `'` still breaks a
  single-quoted assignment by ending the quote early, whereas a quoted
  heredoc terminator has no such escape character; only the exact delimiter
  line ends it.
