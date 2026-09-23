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

### Round 5 growth (368 -> 377)

External Tier-3 review (GPT, high, PR #790) found this module's own docstring
promise — "NEVER touches `kind == "section"` state" — enforced only for
`cmd_next_batch`, not `cmd_release`: a wrong `--state` path or a caller
unaware of the new CLI could write the 9-state vocabulary into a legacy
section row's `status` field. Fixed with the same `state.get("kind") !=
"sub_iterate"` gate `cmd_next_batch` already had, plus one regression test
proving a section-kind unit is left untouched. Not a new responsibility — a
completeness fix to a guard this module already owned in part.

### Round 6 growth (377 -> 392)

External Tier-3 review (GPT, high, PR #790) found `cmd_next_batch` accepted
any `branch_strategy` — including the deprecated `"stacked"` (still only a
soft warning at write time, `campaign_init.py`) and the `"single-branch"`
default — without checking whether `_resolve_batch_base` actually resolved a
usable base. `_ancestry_ok` returns `True` unconditionally for a
dependency-free unit regardless of `base_branch`, so a `None` base silently
claimed those units with `"base_branch": null` in the payload, while
dependency-bearing units stalled forever with no error explaining why (their
own `_ancestry_ok` call fails closed on the missing base, but nothing ever
surfaces that as the actual cause). Fixed by rejecting a `None` base up
front — before any ancestry/claim processing — with a clear "no batch base
for next-batch" error, exit 1. Not a new responsibility — a completeness fix
to the base-resolution boundary this module already owned; one new
regression test proving a stacked-strategy state errors out rather than
producing a null-base claim.

### Round 10 growth (392 -> 404)

External Tier-3 review (GPT, high, PR #790) found `cmd_next_batch` validated
`state.get("kind") == "sub_iterate"` only on its outside-lock peek
(`_load_state` before `loop.lock` is acquired), then reloaded state
inside the lock and proceeded straight to computing the ready set and
claiming units without rechecking `kind` on that fresh read. A concurrent
`cmd_init` replacing the state file with a `kind == "section"` one in the
window between the peek and the lock acquisition would let this command
write 9-state fields (`status`, `attempt`, `attempt_id`, `lease_expires_at`)
into a legacy section campaign's units — exactly the guarantee this
module's own docstring already promised never happens, just missed on the
locked-reload path (Round 5 closed the same gap for `cmd_release`). Fixed
by re-checking `kind` immediately after the locked `_load_state` call,
before any unit is inspected or mutated, returning the same "next-batch is
only valid for kind == 'sub_iterate'" error (exit 1) used by the
outside-lock check. Not a new responsibility — closing the same guarantee
against the same race window `cmd_release` was already closed against;
one new regression test (`test_recheck_kind_after_lock_prevents_a_section_
state_race`) forces the peek and the locked reload to disagree on `kind`
and asserts the unit is left untouched.

### Round 11 growth (404 -> 431)

External Tier-3 review (GPT, high, PR #790) found `cmd_next_batch`'s
`ancestry_confirmed` set is only as good as the `depends_on` edge set it
was computed against at the outside-lock peek. A concurrent writer that
ADDS a brand-new edge to an already-`pending` unit between the peek and
the locked reload is invisible to the existing SHA-staleness check
whenever the new dependency was already `merged` before the peek and its
`merged_commit` never changes in that window: `_snapshot_merged_commits`
records every merged unit regardless of whether it was a dependency yet,
so the pre/post comparison for the newly-added edge passes vacuously —
the unit could be claimed with a dependency `_ancestry_ok` never actually
verified. Fixed by additionally snapshotting each pending unit's exact
`depends_on` edge SET at peek time and requiring the locked reload's set
to match exactly (case-folded, matching every other dependency lookup in
this module); a unit whose edge set changed at all is excluded this
round rather than trusted on a verification that covered a different
set, and picked up again on the next `next-batch` call's own fresh
outside-lock pass. One new regression test adds a fresh edge to an
already-merged, SHA-unchanging dependency between the peek and the lock
and asserts the unit is excluded. Not a new responsibility — extending
the same "peek-time verification must still describe the locked state"
principle the SHA-snapshot check and Round 10's `kind` recheck already
established, to the one input surface (the edge set itself) neither
covered.

### Round 12 growth (431 -> 442)

External Tier-3 review (GPT, high, PR #790) found `cmd_release` accepted
any `--max-attempts` argparse gives it `type=int` on, including zero and
negative values, with no range check. `unit.get("attempt", 0) + 1 >=
args.max_attempts` is then trivially true for any such value — `attempt`
is always `>= 0`, so a zero/negative budget marks every released unit
`failed` on its very first retry, silently, with no valid attempt budget
ever having existed. Fixed by validating `--max-attempts` as a positive
integer up front, before the lock is even acquired, mirroring
`cmd_next_batch`'s own pre-existing `--max-parallel` validation (Round 6
context) — same shape, same "reject before any state is touched"
placement. Not a new responsibility — completing the same CLI-argument
validation coverage this module already gives its other numeric flag.

### Round 13 growth (442 -> 481)

Not an external-review finding this time — a self-discovered, CI-blocking
regression surfaced while re-verifying round 12's fix: CI's `Shared tests
(Windows)` failed on the round-12 push with a `PermissionError` in
`test_n_concurrent_claimers_never_double_claim`'s real-subprocess stress
test, and local re-runs of the SAME unmodified test reproduced it
independently (~1-in-4 to ~1-in-6), proving it a pre-existing
architectural gap rather than something round 12 introduced. Root cause:
`_load_state`'s outside-lock peek and `_save_state`'s locked
`tmp.replace(state_path)` can transiently deny EACH OTHER a
`PermissionError` on Windows — `os.replace` needs to briefly hold the
destination exclusively and Python's default `open()` does not request
`FILE_SHARE_DELETE`, a window POSIX rename has no equivalent of (the
module's own "atomic tmp+replace means no lock is needed just to read"
assumption is true on POSIX, false on Windows). Both a reader-denied and
a writer-denied variant were reproduced locally. Fixed by routing both
`_load_state` and `_save_state`'s replace through one shared
`_retry_on_transient_permission_error` helper (5 attempts, short linear
backoff, retrying only `PermissionError` — a persistent, non-transient
permission problem still surfaces once the budget is exhausted). Verified
with 8 consecutive clean re-runs of the concurrency stress test after the
fix (vs. failures within the first handful before it) — a probabilistic
race needs more than one green run to trust. `autonomous_loop.py` and
`loop_mark.py` carry their own separate `_load_state`/`_save_state`
copies with the same theoretical exposure (ADR-045: never a shared
import) — NOT touched here, since no test currently demonstrates them
failing; left as a documented, not-yet-observed risk rather than
speculative preemptive work.

### Round 14 growth (481 -> 497)

Not an external-review finding either — round 13's own fix commit
(`043d2d3aa`) still failed `Shared tests (Windows)` in real CI with the
IDENTICAL `PermissionError` signature in
`test_n_concurrent_claimers_never_double_claim`, discovered while
investigating an unrelated CI-dispatch delay on the same PR. This is
significant: round 13's 8-consecutive-clean LOCAL stress-test verification
did not transfer to the loaded, shared CI runner, where 20 real
subprocesses under actual resource contention produce longer
`PermissionError` windows than an idle local machine ever does — a
probabilistic race's local pass streak is not proof it is fixed under
heavier contention elsewhere. Round 13's retry budget (5 attempts, ≤50ms
total backoff) was simply too short a window for that contention to
clear. Fixed by widening `_TRANSIENT_PERMISSION_RETRY_ATTEMPTS` to 30 and
capping the linear backoff at 0.1s/attempt (worst case ~2.5s total,
still short enough that a persistent, non-transient permission problem
surfaces in seconds, never silently hangs). No test-shape change was
needed — `shared/tests/test_loop_claim_load_state_retry.py`'s assertions
read the constant rather than hardcoding `5`, so they cover the new
budget without edits. CodeQL flagged the first version of this change
(`raise last_exc` where `last_exc: PermissionError | None` was still
statically `None`-typed even though the positive constant guarantees the
loop body executes) as an "Illegal raise" error — fixed by dropping the
`last_exc` variable entirely and re-raising via a bare `raise` on the
final attempt instead, which also drops the previously-wasted sleep
before that final raise.

### Round 16 growth (497 -> 502)

A SEPARATE, PRE-EXISTING GHAS CodeQL alert ("Explicit returns mixed with
implicit (fall through) returns", `_retry_on_transient_permission_error`)
had sat as an unresolved PR review thread since round 13 — it never
failed the CodeQL check itself (not a NEW alert on any later diff), but
`main-protection`'s `required_review_thread_resolution` rule blocks
merge on ANY unresolved thread regardless of check status, and this one
was discovered only when investigating why the PR stayed
`mergeStateStatus: BLOCKED` after round 15's fix made every check green.
Same root cause as round 15's `_TRANSIENT_PERMISSION_RETRY_ATTEMPTS`-is-
always-positive assumption: the loop's `return fn()` (success) and
`raise` (final failure) paths never actually fall through, but CodeQL
cannot prove that from the positive literal alone, so an implicit
`return None` fall-through path is still statically reachable. Fixed
with an explicit terminal `raise AssertionError(...)` instead of letting
the function body end implicitly — same "raise the unreachable case
explicitly" pattern already applied elsewhere in this codebase.

### Round 17 growth (502 -> 511)

External Tier-3 review (GPT, PR #790 round 17) BLOCKed on a genuine bug,
verified against the code: `cmd_release` resolves `--unit` via
`find_unit_row`'s case-folded fallback and correctly mutates the matched
row's status, but then passed the CALLER's raw `args.unit` spelling
straight through to `_cleanup_unit_worktree`, which recomputes the
worktree path from that string. A case-mismatched `--unit` (e.g. `r4`
against a stored canonical `R4`) makes the recomputed path wrong; on a
case-sensitive filesystem (Linux CI) `wt_path.exists()` is then False and
cleanup silently no-ops (best-effort, never blocking) — the real
worktree and branch are left behind with no error. Fixed by capturing
`unit["id"]` (the canonical spelling `find_unit_row` actually matched)
inside the lock and passing that to `_cleanup_unit_worktree` instead of
`args.unit`. Regression test:
`test_loop_claim_release_cleanup.py::test_release_cleanup_uses_canonical_unit_id_not_caller_casing`.

## Consequences

- Every downstream campaign-dag-scheduler sub-iterate (R5a, R5b, R6) that
  touches `loop_claim.py` operates against the current 511-line ceiling (see
  Round 17 growth above), not 300 — the next crossing needs its own ADR.
- New tests for `_cleanup_unit_worktree`, the ADR-045 dispatch-identity
  regression, and the transient-`PermissionError` retry live in sibling
  files, `shared/tests/test_loop_claim_release_cleanup.py` (`cmd_release`'s
  own coverage), `shared/tests/test_loop_claim_mark_dispatch.py` (the
  ADR-045 dispatch regression, moved out round 12), and `shared/tests/
  test_loop_claim_load_state_retry.py` (round 13) — all split from
  `test_loop_claim.py` purely to keep every file under the 300-line
  guideline; no baseline implication, none of these files' own limits
  changed. Round 10's kind-recheck regression test pushed
  `test_loop_claim.py` back over 300 lines a second time; `TestCmdRelease`'s
  basic status-transition tests moved into `test_loop_claim_release_
  cleanup.py` (which already owned the rest of `cmd_release`'s coverage)
  to bring both files back under the guideline. Round 11's dependency-race
  regression test brought `test_loop_claim.py` to exactly 300 lines — at,
  not over, the guideline. Round 12's two `--max-attempts` validation
  tests pushed `test_loop_claim_release_cleanup.py` to 307; rather than
  further crowd `test_loop_claim.py` (already at the guideline) or that
  file, the ADR-045 dispatch-identity class — never actually about
  `cmd_release` — moved to its own new sibling.

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
