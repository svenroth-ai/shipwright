# Serial merge lane: review pinning, staleness cascade, STRICT-STOP

## Context

`campaign-mode.md` steps 3f-bis through 3i (built by R1-R4) described the
serial merge lane the wave-based autonomous loop uses to review and merge
each sub-iterate, but left four gaps: (1) review attribution was asserted
only loosely before the reviews.json commit; (2) `shipped_head` was
dual-written (a legacy path from R3) instead of read once from
`review_pin.json`; (3) nothing confirmed the PR's actual merge commit SHA
before recording `merged`; (4) `STRICT-STOP` had no drain semantics, so a
mid-wave abort could strand `running`/`merging` units and never release the
session lock.

## Decision

Revise campaign-mode.md 3f-bis..3i and step 4 to add: an exact
`HEAD == reviewed_head` assert before the reviews.json commit (with
delete-pin + demote-and-reenter on deviation) plus a post-commit
commit-parent assert; read `shipped_head` from `review_pin.json` directly at
3g; a PR-identity verification (node id, head ref, base ref) before merge, in
addition to `--match-head-commit`; a bounded post-MERGED poll for
`mergeCommit.oid` with strict-SHA validation, recorded via
`loop_claim.py::cmd_mark_merged`; a currency check while `reviewed` (not
`merging`), bounded against a persistent `UNKNOWN` mergeability, promoting
`reviewed -> merging` only once current; a rebase-triggered staleness cascade
(`max_rebase_reviews=2`) that actually invokes `ensure_current.py`, resets
its counter on a fresh attempt, and unconditionally deletes the pin +
demotes `reviewed -> built` as its first action; a new `campaign_drain.py`
module implementing STRICT-STOP as sweep-then-bounded-drain, guaranteeing
every non-terminal unit reaches a terminal status before `cmd_finalize`
runs and the session lock releases; and a step 3h status-vocabulary mapping
onto `campaign_progress.py`'s existing 5-token enum (no new token).

## Consequences

The merge lane now provably reviews and merges exactly the diff it pinned,
never merges the wrong PR object, records a validated merge SHA (never a
guessed `git rev-parse origin/{default}`), recovers from a rebase without
re-reviewing stale content, and a STRICT-STOP always leaves the campaign in
a finalizable, lock-released state instead of wedging it.

## Rationale

Reusing `audit_compliance_lifecycle.py::_merge_sha`'s SHA-shape guard and
`cmd_mark`'s audited override avoids two independently-maintained
validators and a duplicate fencing mutator; keying the staleness cascade off
an actual rebase of the unit's OWN branch (not `origin/<default>` merely
advancing) avoids invalidating every sibling unit's pin on every unrelated
merge in the same wave.

## Rejected alternatives

A new fencing-token mutator dedicated to each demotion — rejected in favor
of the existing `cmd_mark` escape hatch. Keying staleness off base-SHA drift
instead of the unit's own branch tip changing — rejected: it would
needlessly re-run the review cascade on every other in-flight unit each time
any one sibling merges. See spec-ref for full findings dispositions,
self-review, and confidence-calibration detail.

## External Plan Review Findings

Both reviewers (glm, openai) returned `revise`, converging on: (a) whether
`cmd_mark_merged` already exists (R4) or is new to R5b — **verified against
actual code**: `git log -1 -- shared/scripts/lib/loop_mark.py` shows it was
last touched by R4's own commit (`ba65b33b4`, PR #790) and is untouched in
this diff — the spec's "new" wording is a drafting artifact; **rejected,
verified false alarm**. (b) stuck-`merging` drain termination — **verified
already handled**: `campaign_drain.py::drain_once` already force-transitions
`merging -> held` (`drain_timeout`) at the bound; the mini-plan's own summary
was merely imprecise — **rejected, already correct**. (c) `swept_after_build`
resume re-entry point — the R5b spec itself (line 76-77) mandates resume via
`held -> pending` with a fresh attempt, not re-entry at 3f-bis reusing the
old PR/worktree — **rejected, per spec's own explicit design**; the
resulting abandoned-PR accumulation is a known, accepted residual gap
(follow-up triage candidate, not in this unit's AC list). (d) crash-safety
of the session-lock release if the drain process itself dies before
`cmd_finalize` — **accepted as a documented, scoped-down claim**: the
"release on every path" language was corrected to mean every path that
reaches the release line, not survival of an uncaught process death;
`stale_after_seconds` reclaims the lock the same way it would for any other
stuck holder. (e) `cmd_mark`'s use as a normal transition mechanism
(openai) — **rejected, per spec's own explicit design**: R5b-merge-lane.md
directs exactly this reuse of the existing audited override rather than a
new mutator per demotion.

## External Code-Review Findings

Both reviewers converged on two HIGH-severity, code-verified gaps, now
fixed: (1) 3g's pre-merge check verified only the head SHA
(`--match-head-commit`), never the PR's own identity (node id / head ref /
base ref) against the pin's `pr_node_id`/`pr_head_ref`/`pr_base_ref` fields
(already recorded by R3's `pin()`, unused until now) — **accepted-and-fixed**:
added a fresh `gh pr view --json id,headRefName,baseRefName` comparison
before `gh pr merge`. (2) the rebase cascade only *described*
`ensure_current.py`/`integrate_main.py` in a comment without an actual
checked invocation, so a `CONFLICTING` branch never actually got rebased —
**accepted-and-fixed**: added a real, checked `ensure_current.py` call
(mirrors F11.md's own pre-merge refresh), demoting to `held`
(`rebase_conflict`, added to the step-3h mapping table) on a genuine
non-resolvable conflict. MEDIUM findings, all **accepted-and-fixed**:
`UNKNOWN` mergeability promoted immediately — added a bounded 6x5s poll
before falling back to treating a persistent `UNKNOWN` as current; the
reviews.json commit's parent was never checked against `reviewed_head` —
added a post-commit assert with the same invalidate+demote recovery as the
pre-commit one; `rebase_count` never reset across a fresh attempt — added a
reset at 3b (step where a new `attempt_id` is minted); step 4's drain/
finalize/release block had no `||` chaining, unlike every other command in
this doc — added `|| STRICT-STOP` on both, and widened `campaign_drain.py`'s
CLI exception handling from `(ValueError, TimeoutError)` to `Exception` so a
corrupted-state crash exits cleanly rather than with an uncaught traceback.
A stray `err.log` scratch file was deleted. Two findings **rejected, with
reason**: (a) a full 3-cycle rebase-to-`held` workflow test — the counting
logic lives in this doc's own bash (`rebase_count` arithmetic), not in any
Python module, so it is exercised by the existing prose guard
(`test_max_rebase_reviews_is_two_and_exhaustion_demotes_to_held`) rather
than a Python-level simulation that could not actually run the bash; (b) the
`test_check_review_attribution_invalidate.py` filename now covers more than
`--mode invalidate` — kept as-is (documented in the file's own new class
docstring) rather than fragmenting one more file for each real-git
scenario sharing the same fixture setup. The required "two sequential
merges, shipped_head/PR-identity at merge time" composition test —
**accepted-and-fixed**: added
`TestTwoSequentialMergesComposition::test_shipped_head_and_pr_identity_survive_two_sequential_merges`.

## Self-Review

7/7 items pass — see `reviews.self` in the review-record (run_id
`iterate-2026-09-24-r5b-merge-lane`) for the full per-item detail, including
the two ADR-024 producer/consumer boundaries probed round-trip via real git
(`review_pin.json`'s `pin()`/`ship()`/`verify()` cycle;
`loop_state.json`'s `units[].status` through `campaign_drain.py`'s sweep and
`cmd_finalize`).

## Confidence Calibration

Two boundaries probed, both round-tripped on real git via the
`git_origin_repo` fixture (no mocking): `review_pin.json` (pin -> ship ->
verify -> invalidate -> re-verify absent, plus the new two-sequential-merges
composition test) and `loop_state.json` (sweep -> poll-drain -> confirm
every unit reaches TERMINAL). Findings from the two rounds of external
review (both plan and code) drove concrete fixes each time — the asymptote
was reached only after this second round returned no further HIGH findings
on the corrected text.
