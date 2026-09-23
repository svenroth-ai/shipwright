# Bloat exception — `shared/scripts/lib/loop_claim.py` raised to 353-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r4-state-mechanics-loop-claim-bloat.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-23
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r4-state-mechanics` (campaign
  `campaign-dag-scheduler`, sub-iterate R4). The limit was crossed fixing a
  real defect a Stage-1 spec-review re-check surfaced against this same
  sub-iterate's initial push: `cmd_release` did not implement the physical
  worktree/branch cleanup the sub-iterate's own spec requires (`.shipwright/
  planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/
  R4-state-mechanics.md` § Fencing — "reclaiming a lease is immediate and
  purely logical; physical cleanup ... is best-effort and never blocks").

## Context

`loop_claim.py` was 300 lines at the sub-iterate's initial merge attempt —
exactly at the AC's stated ceiling, achieved precisely by splitting the
identity-checked mutators out into the sibling `loop_mark.py` (see that
module's docstring and the sibling bloat-exception precedent this ADR
follows, `iterate-2026-09-22-r4-state-mechanics-loop-state-bloat.md`). A
Stage-1 spec-reviewer re-check on the resulting PR found `cmd_release`
silently omitted the cleanup half of the spec's own "reclaim/cleanup split"
— the logical `claimed -> pending|failed` transition was implemented, but
the accompanying best-effort `git worktree remove` / `git branch -D` was
not. Fixing this — `_cleanup_unit_worktree`, its two new `--campaign-slug`/
`--campaign-worktree` CLI arguments, and the recomputed-path safety
docstring the spec's own security-hardening note requires — added 45 lines
after trimming what could be trimmed without cutting the safety rationale
(why the path is recomputed rather than trusted, why the branch name is
read back from git instead of stored). That is a real, spec-mandated
responsibility this module already owned in part (release) and had failed
to complete, not a new feature.

## Ousterhout Argument

`_cleanup_unit_worktree` shares its entire vocabulary with `cmd_release`
(the same `(campaign_slug, unit_id, attempt)` triple the release row itself
carries) and has exactly one call site, immediately after the logical
release it complements. Extracting it into a third module would separate
two halves of one spec-named split ("reclaim" and "cleanup") that this same
project's own spec text treats as a single decision, not two independently
varying concerns — the split this campaign's AC actually rewards is one
drawn at a genuine SEAM (scheduling decisions vs. identity-checked
mutations, `loop_claim.py` vs. `loop_mark.py`), not at "this function is a
few lines that happen to call `subprocess`."

## YAGNI Check

Not speculative: the spec's own Fencing section names this exact behavior
("physical cleanup ... is best-effort and never blocks") as part of R4's
scope, and the Stage-1 spec-reviewer's re-check treated its absence as a
real defect against this sub-iterate's own acceptance criteria, not a
future nice-to-have.

## Chesterton-Fence Check

No prior version of `cmd_release` existed without this gap being a known,
spec-named requirement — the fence being removed here is the gap itself
(an incomplete implementation of an already-specified behavior), not a
deliberate prior design choice.

## Decision

Raise `current` for `shared/scripts/lib/loop_claim.py` from **300 to 345**,
`state: "exception"`, `adr: "ADR-pending:
.shipwright/planning/adr/iterate-2026-09-22-r4-state-mechanics-loop-claim-bloat.md"`,
in the same commit as this fix. **Retirement plan:** re-review at
2026-12-22 alongside the sibling `loop_state.py` exception — if R5a's real
runner-brief wiring reveals `_cleanup_unit_worktree` needs its own
`{desc}`-aware branch-naming logic (today it reads the branch back from
git rather than recomputing the full spec formula, since R4 itself has no
`{desc}` context — see the review-findings ADR), that growth may justify
extracting a small `loop_release.py` at that point, once R5a's real call
shape is known rather than guessed now.

### Round 2 growth (345 -> 347)

Orchestrator-level spec re-review (non-blocking note) found
`_cleanup_unit_worktree`'s docstring stated the `git worktree prune`
fallback as though it already existed in this codebase, giving a reader
the same false impression the review-findings ADR's finding #5 correction
had just removed from the disposition record. Qualified the docstring to
say the fallback is spec-named but not yet implemented.

### Round 3 growth (347 -> 353)

Stage-2 code-review finding (medium, correctness): `_snapshot_merged_commits`
keyed its `{unit_id: merged_commit}` map by exact-case `u["id"]`, but every
other dependency lookup in this module (`_ancestry_ok`'s `by_id`) case-folds,
because `campaign_graph.validate_dependency_graph` accepts a case-mismatched
`depends_on` edge at write time. For such an edge, both the pre- and
in-lock snapshots returned `None`, letting the staleness comparison pass
vacuously — silently defeating the check for exactly the edge shape the
case-fold convention exists to handle. Fixed by case-folding the snapshot's
key and the comparison-site `dep_id` lookup, matching the existing
convention exactly (`str(x).lower()`). Not a new responsibility — a
correctness fix to one already counted above.

### Round 4 growth (353 -> 368)

Stage-3 doubt review (HIGH #4): `_cleanup_unit_worktree` (this same Round 3's
own fix — see this ADR's earlier commit) is completely inert in production —
`resolved_worktree_path`'s first parameter is `main_root` (the repo root
ABOVE `.worktrees/`), but `campaign_worktree` (this function's own parameter)
is ALREADY `<main_root>/.worktrees/campaign-{slug}`, computing a doubled,
nonexistent path that always hit the `wt_path.exists()` guard and silently
no-op'd the entire cleanup. Fixed by resolving the real `main_root` first via
`lib.git_base.main_repo_root` (the same helper `setup_unit_worktree.py`
already uses for this exact purpose) before calling `resolved_worktree_path`.
Not a new responsibility — a correctness fix to the physical-cleanup
primitive already counted in Round 3 above; the growth is the fix itself
plus a REAL (non-mocked) regression test proving actual git calls fire
against the correctly-recomputed path (`shared/tests/
test_loop_claim_release_cleanup.py`'s prior 5 tests all mocked
`resolved_worktree_path` away, which is exactly how this bug went
undetected).

## Consequences

- Every downstream campaign-dag-scheduler sub-iterate (R5a, R5b, R6) that
  touches `loop_claim.py` operates against the current 368-line ceiling (see
  Round 4 growth above), not 300 — the next crossing needs its own ADR.
- New tests for `_cleanup_unit_worktree` and the ADR-045 dispatch-identity
  regression live in a new sibling file, `shared/tests/
  test_loop_claim_release_cleanup.py` (split from `test_loop_claim.py`
  purely to keep both under the 300-line guideline; no baseline
  implication — neither file's own limit changed).

## Rejected alternatives

- **Split `_cleanup_unit_worktree` into a new `loop_release.py`.** Rejected
  per the Ousterhout argument above: one call site, one shared vocabulary
  with `cmd_release`, no independent variation — a split here would be
  exactly the "purely from feature count, not genuine cohesion" case the
  sub-iterate's own Acceptance Criteria says to avoid, in the opposite
  direction the `loop_mark.py` split (a genuine seam) demonstrates.
- **Skip the cleanup fix; defer to R5a as the original (now-corrected)
  review-findings disposition claimed.** Rejected: that disposition rested
  on a factual error (no `git worktree prune` call exists anywhere in
  `shared/scripts/` today to sweep a failed cleanup) and on treating the
  spec's "best-effort and never blocks" as license to omit the attempt
  entirely, when the spec requires the attempt and only excuses a failed
  one.
- **File no exception; let the post-merge Group H detective audit surface
  it.** Rejected for the same reason the sibling `loop_state.py` ADR
  rejects it: the crossing is certain and immediate, not a maybe — filing
  now, in the same diff, is the documented anti-ratchet-compliant path.
