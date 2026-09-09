# Non-converging PR-review halt (exit 8)

**Run:** iterate-2026-09-09-pr-review-nonconverging-halt (trg-ac24ec5b, PR #690)

## Context

PR #690 pushed ten times over ~7h40m, blocked by the Tier-3 `PR Review` gate
every time; nine of twelve verdicts restated one finding in different words as
line numbers drifted underneath it. F11's existing `checks_failed` exit (2)
tells the operator "diagnose, fix, re-push" — sound advice when each round's
BLOCK names a new, distinct defect, unsound when round after round names the
same one. The loop's cost is wall-clock, not tokens, so a spend-keyed guard
stayed quiet through the whole thing.

## Decision

Add exactly one new terminal exit code, `EXIT_NON_CONVERGING = 8`, to
`deliver_pr.py`'s ladder, triggered when the last two `PR Review` BLOCK
comments on a PR share a recurring (file, claim) finding: exact file-path
match plus a claim-vocabulary overlap coefficient past a tuned threshold
(`lib.pr_review_convergence`). Two more preconditions gate the escalation
(`lib.pr_review_verdict_provenance`): the BLOCK comments must be
authentically-authored (real bot login, unedited, AND correlated to a sibling
`CHANGES_REQUESTED` review posted within seconds — not login alone, which
another same-repo workflow like `bloat-check.yml` can also post under), and
must bind to two distinct, current commits via that same sibling review's
GitHub-stamped `commit.oid` (falling back to a `commits[]`/`committedDate`
approximation only when review data itself is unavailable). Exit 8 is
TERMINAL in F11 exactly like exit 3 (closed unmerged) and exit 6 (no merger
can exist) — it never suggests "re-run to keep trying."

## Consequences

A run stuck restating one PR-review finding now stops burning wall-clock
after round 2 (not round 10) and hands both verdicts to a human, quoted side
by side, instead of silently looping. The predicate adds no memory to the
`PR Review` gate itself (`pr_review.py` stays stateless per commit, reads
nothing here), never makes a review more lenient or blocks an
otherwise-passing merge (it only ever replaces an existing `checks_failed`
verdict with a stricter one), and adds no new Required Check or workflow
change. `deliver_pr.py` now also reads the PR's `reviews` array
(`gh pr view --json …,reviews`) — a new external read this component did not
make before — for the commit-binding/authenticity fix; see the architecture
doc bullet for this run_id.

## Rationale

Loose-on-text/strict-on-location was chosen over exact string equality
(never fires on reworded prose — measured 9 shared tokens, 0.32 overlap
coefficient on PR #690's own round-1/round-2 bytes) and over a push-count
threshold (wrong axis: a genuinely converging run needing 4 rounds of
distinct real findings is the common, good case a count would cut short; the
signal that separates that from a stuck run is sameness, not volume — on
#690 sameness fires at round 2, saving ~7h, where a count tuned to catch #690
early would still burn most of the wasted time on the common case's false
positives). Commit-binding was upgraded mid-review from an inferred
`committedDate` guess to GitHub's own `reviews[].commit.oid` stamp after a
Stage-3 doubt review found the guess had both a false-positive and a
false-negative failure mode, and the authoritative source needed no producer
change — verified live against PR #690, whose `commits[]` history was lost to
an unrelated rebase but whose `reviews[].commit.oid` survived intact. That
same correlation also closes a login-only forgery gap the doubt review found
concrete (not hypothetical): `bloat-check.yml` posts PR comments under the
same bot login from attacker-nameable file paths, and its real comment format
already matches the shape this predicate parses.

## Rejected alternatives

A push-count threshold ("stop after N pushes") — wrong axis, see Rationale.
Adding a producer-side nonce marker to the issue comment itself (mirroring
`pr_review_dismiss_select.py`'s review-dismissal marker) — a larger,
out-of-scope change to `pr_review.py`'s posting protocol; the review-based
correlation achieves the same authenticity proof using data already posted,
with no producer change. Tracking whether an intervening APPROVE resets the
BLOCK pair — declined for now; PR #690's own 12 verdicts contain no
intervening APPROVE, so there is no real-data case motivating the added
complexity yet (disclosed in the iterate spec; revisit if a future incident
shows it firing).

## Test Completeness Ledger

See `.shipwright/planning/iterate/iterate-2026-09-09-pr-review-nonconverging-halt.md`
(33/33 rows tested) for the full ledger, threshold provenance, and the
Stage-2/Stage-3 review triage this decision reflects.
