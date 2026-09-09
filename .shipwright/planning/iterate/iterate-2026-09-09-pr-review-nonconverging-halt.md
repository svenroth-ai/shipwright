---
run_id: iterate-2026-09-09-pr-review-nonconverging-halt
status: draft
type: change
complexity: medium
---

# Iterate: PR-review non-converging halt (F11 exit 8)

## Origin

trg-ac24ec5b. Sub-iterate P3.5 (campaign `req3-04c-ac-identity-wave2`, PR #690,
2026-09-08) pushed ten times between 09:46Z and 17:26Z, blocked by the Tier-3
`PR Review` gate every time — twelve verdicts counting the two local rounds,
nine of the twelve restating one finding ("promotion trusts coverage/tests
without establishing the evidence came from a CI run bound to the current
commit/manifest revision") against whichever line had moved. F11's exit-2
sentence ("Diagnose, FIX, re-push, then re-run delivery") has no counter, no
memory of the previous round, and no way to notice it is being executed for
the tenth time against the same objection. Cost: ~7h40m wall-clock. A
spend-keyed guard would have stayed quiet the entire time — the context-cost
meter read 1305 calls / $127.46 with only ~112 of those after the F5b fold —
because the loop's cost is wall-clock, not tokens.

## Spec Impact: NONE

No target-app FR in `shipwright_sync_config.json` names any file this diff
touches — this is shipwright's own delivery tooling (framework, not a target
app), so `change_type` is the no-FR branch. `affected_frs: []`.

## What changed

- **`shared/scripts/lib/pr_delivery.py`** — one new constant,
  `EXIT_NON_CONVERGING = 8`, added to the existing closed exit-code vocabulary.
  Not added to `STATUS_EXITS` — `"non_converging"` is not a raw watch status,
  it is coined by the new escalation layer below.
- **`shared/scripts/lib/pr_review_convergence.py`** (new) — the pure sameness
  predicate. No `gh`, no host, testable on plain dicts: `extract_blocking_findings`
  parses a `PR Review` comment's `### 🚫 Blocking issues` bullets into
  `{files, tokens}`; `findings_recur` matches two findings on an exact file
  path (strict) and a claim-vocabulary overlap past a threshold (loose);
  `non_converging` is the public entrypoint over a `gh pr view --json comments`
  payload.
- **`shared/scripts/lib/deliver_pr_non_converging.py`** (new) — the
  host-touching glue: fetches the PR's comments, calls the predicate, and
  turns a match into the escalated `non_converging` / `EXIT_NON_CONVERGING`
  delivery result. Split out (mirroring `lib.pr_self_merge`, `lib.pr_delivery`)
  because `deliver_pr.py` already carries an anti-ratchet bloat exception
  (ADR-122) and this keeps the growth to the minimum the new capability
  actually needs.
- **`shared/scripts/tools/deliver_pr.py`** — `deliver()`'s `_body()` now pipes
  every ladder result through `escalate_if_non_converging` (a no-op unless the
  ladder's own verdict was `checks_failed`); `summary()` gains a
  `non_converging` branch.
- **`plugins/shipwright-iterate/skills/iterate/references/F11.md`** — one new
  arm in the `case "$?"` block, exit 8, terminal exactly like 3 and 6 (no
  "re-run to keep trying" wording).
- **`docs/hooks-and-pipeline.md`** — one new paragraph documenting the
  escalation where the existing "Delivery is the MERGED PR" section already
  describes the exit-2 sentence this unit adds an exception to.
- **`shipwright_bloat_baseline.json`** — `deliver_pr.py`'s `current` bumped
  331 → 340 under its existing `state: exception` / `ADR-122` entry (measured,
  not estimated — see Test Completeness Ledger).
- **`plugins/shipwright-security/tests/test_pr_review_render_convergence_canary.py`**
  (new) — one canary test pinning the three literals `pr_review_convergence.py`
  depends on (`"Shipwright PR Review"`, `"🔴 BLOCK"`, `"Blocking issues"`),
  added after Internal Plan Review flagged the cross-root literal duplication
  as untested (see Internal Plan Review below). Split into its OWN file
  (rather than added inline to `test_pr_review_render.py`) when that edit
  pushed the existing file to 314 lines — the bloat Stop-hook's "just
  crossed the limit" rule applies to a file that grows past 300 in this
  session even by one added test, and a standalone canary file was the
  cleaner fix over trimming unrelated existing tests.
- **`shared/scripts/lib/pr_review_verdict_provenance.py`** (new) — the
  authenticity (`is_authentic`) and commit-binding
  (`verdicts_span_distinct_commits`) preconditions, split out of
  `pr_review_convergence.py` for the same bloat-gate reason once those two
  fixes (below) pushed that file to 302 lines.
- **`shared/tests/test_deliver_pr_non_converging.py`** (new) — the
  non-converging end-to-end ladder tests, split out of `test_deliver_pr.py`
  for the same reason once the fix-driven tests pushed that file to 307
  lines. `test_deliver_pr.py` itself is unchanged from its pre-session
  state — every addition relocated cleanly.
- **`shared/scripts/lib/pr_review_verdict_provenance.py`** (Doubt Review
  follow-up) — `verdicts_span_distinct_commits` now accepts `reviews` and
  prefers each comment's sibling `CHANGES_REQUESTED` review's GitHub-stamped
  `commit.oid` over the `commits[]`/`committedDate` approximation, falling
  back to the approximation only when `reviews` itself is empty; the same
  correlation also closes the login-only forgery gap structurally (see Doubt
  Review section below). `_commit_as_of`'s tie-break fixed (array order, not
  oid text).
- **`shared/scripts/lib/pr_review_convergence.py`** / **`deliver_pr_non_converging.py`**
  (Doubt Review follow-up) — `non_converging`/`escalate_if_non_converging`
  thread the new `reviews` parameter through; the `gh pr view --json` field
  list gains `reviews`.
- **`shared/tests/test_pr_review_verdict_provenance.py`** (new) — the
  provenance module's own tests: real-review binding, the forged-comment
  non-bind case, the empty-`reviews` fallback regression guard, and the
  tie-break fix.
- **`shared/tests/_pr690_review_fixtures.py`** — `round_reviews()` added:
  PR #690's REAL `CHANGES_REQUESTED` reviews, re-fetched live during doubt
  triage (`commit.oid`, `submittedAt`, both real — survived the rebase that
  made `round_commits()`'s data synthetic).

## Internal Plan Review + External LLM Review — findings and triage

Both the internal reviewer (`shipwright-plan:opus-plan-reviewer`) and both
external reviewers (openai/codex, glm/openrouter) converged independently on
the same two structural gaps in the first build. Triaged per the protocol —
fix / disclose / decline, always with a reason:

**FIXED — commit binding (openai HIGH #1; internal-review architecture-medium).**
`non_converging` took the two most recent BLOCK comments with no check that
they reviewed different code. A stage-1 re-run (the documented remedy for the
GLM JSON-parse flake — `project_pr_review_glm_json_parse_flake` memory: "rerun,
don't escalate") posts a second BLOCK for the SAME commit; a transient
`PR Review` failure with no new BLOCK can leave a stale verdict as "most
recent". Either would have escalated on "the fix is not addressing it" when
no fix was attempted at all. Fixed by
`verdicts_span_distinct_commits(commits, head_sha, previous, current)`
(`lib.pr_review_verdict_provenance`):
requires the current BLOCK to bind to the PR's actual `headRefOid` and the
previous BLOCK to bind to a DIFFERENT commit, both via `_commit_as_of`
(most-recent-commit-at-or-before-`createdAt`, over the PR's own `commits`
array). Fails OPEN (no escalation) whenever `commits`/`head_sha` are not
supplied — the caller contract, not a silent default. `deliver_pr_non_converging.py`
now fetches `comments,commits,headRefOid` in the same `gh pr view` call it
already made.

**FIXED — comment-author authenticity (openai HIGH #2; internal-review security-medium).**
`is_block_verdict` matched on body text alone (`"Shipwright PR Review"` +
`"🔴 BLOCK"`). Any PR commenter could write body text matching those markers
and forge a pair of "verdicts", forcing a terminal exit-8 halt — a
denial-of-delivery gap that directly contradicts `pr-review-run.yml`'s own
stated trust rule ("nothing stage 1 produces may be treated as authoritative").
Fixed by `is_authentic(comment)` (now in the sibling module
`lib.pr_review_verdict_provenance`), checking `comment["author"]["login"] ==
"github-actions"` (the login PR #690's own real comments carry, per
`pr-review-run.yml`'s `secrets.GITHUB_TOKEN`), applied alongside the text
match in `two_most_recent_block_verdicts` — a comment must satisfy both to
count as a verdict.

**FIXED (cheap, low-severity) — renderer-format drift canary (internal-review architecture-low).**
`pr_review_convergence.py` hard-codes three literals produced by
`pr_review_render.render_comment`, in a different plugin/pytest root
(ADR-044 blocks a direct cross-root import). A renderer change would make
this predicate fail open silently forever, with no test catching it. Fixed
by one canary test in the PRODUCER's own root
(`test_block_verdict_marker_and_heading_are_the_literals_convergence_depends_on`)
that reds on drift.

**DISCLOSED, not fixed — the match fires on PARTIAL recurrence, not just a
stuck loop (code-reviewer, Stage 2).** `findings_recur` returns on the FIRST
(file, claim) pair that recurs across the two verdicts — it does not require
that every finding recur, or that the current verdict introduce no new
finding on a new file. PR #690's own acceptance fixture is this shape: round
1 named one file, round 2 named two, one of them new — the round
demonstrably fixed something AND still matched on the one file it did not
fix. That is precisely the loop this unit halts, so the predicate is
correctly tuned to it — but it means "the reviewer restated one deferred
finding while the author fixed everything else" is indistinguishable from
"the loop is stuck," and exit 8 is terminal. Not fixed: requiring the
current verdict to introduce no new-file finding would have made the
predicate NOT fire on PR #690's own real round-1/round-2 pair (ledger row
12), directly contradicting the acceptance criteria this unit was built to
satisfy — the "fix" would break the validated case. Disclosed here, and in
the PR body, as a known false-positive axis distinct from the vocabulary one
below: a partially-converging run that keeps failing on one un-fixed finding
will halt exactly like a fully-stuck one, and the operator reading the
quoted verdicts is the check against that, same as for vocabulary overlap.

**DISCLOSED, not fixed — threshold calibration rests on n=1 real positive
(glm HIGH; internal-review completeness-medium).** `MIN_SHARED_TOKENS=4` /
`MIN_CLAIM_OVERLAP=0.2` are set below one real measurement (9 tokens / 0.32),
not against a corpus of past `PR Review` BLOCK pairs. This repo's review
vocabulary is genuinely repetitive (coverage, manifest, commit, evidence,
provenance), so a false positive on two distinct findings sharing that
vocabulary on the same file is a real, unmeasured risk. Not fixed in this
unit: a corpus back-test needs access to and triage of historical BLOCK pairs
across many PRs, which is a separate investigation, not a code change, and
the brief's acceptance bar was explicitly "the real #690 pair fires, a
synthetic genuinely-distinct pair does not" — met. Mitigated in this unit by
the two binding fixes above, which independently narrow the false-positive
window (same file, same author, ≥4 shared tokens, AND on two distinct,
current commits) — the residual risk is disclosed here and in the PR body,
not hidden.

**DECLINED, out of scope — structural fail-closed blocks are invisible to the
predicate (internal-review completeness-low).** `pr_review.py`'s "nothing was
reviewed" / diff-too-large blocks render an empty `blocking` list, so
`extract_blocking_findings` returns `[]` and this predicate never fires on
them, even though they are the most deterministic repeat-BLOCK shape this
repo actually produces. Declined: it needs a second, zero-heuristic
byte-identity arm — a real but separate change, not a gap in what THIS unit's
acceptance criteria asked for (recurring free-text findings).

**DECLINED, out of scope — campaign-leg terminal treatment (internal-review completeness-low).**
Whether an interleaved-serial campaign driver retries a failed leg on exit 8
the same way it must not retry on exit 3/6 is a real question, but it is
about `campaign-mode.md`'s consumer of F11's exit code, not F11 itself —
same "second escalation channel" boundary the brief drew around
`mid-flight-escalation.md`. Left for a follow-up card.

**DECLINED, out of scope (low severity, narrow blast radius) — multi-line
bullets and file-rename fallback (internal-review architecture-low).**
`_BULLET_RE` reads only the bullet's first line, and `findings_recur`
requires an exact file-path match with no basename fallback for a renamed
file. Both are real, narrow robustness gaps on the LOOSE half of an already
loose-on-text predicate; over-fitting the parser further without more real
multi-line/rename BLOCK examples risks tuning against imagined shapes rather
than observed ones — the same caution the threshold provenance section
argues for on the numeric side.

**VERIFIED, no change needed — a co-failing check does not mask the escalation
(glm low).** `escalate_if_non_converging` checks membership of `PR Review` in
`result["watch"]["failed"]` (a list), not that it is the ONLY failing check —
so a PR with both `PR Review` and, say, the test suite red still escalates
correctly. No fix required; recorded here because the reviewer's concern was
real enough to check, not to wave off.

**DECLINED — `gh pr view --json comments` paging on very long PRs
(internal-review performance-low).** Unverified whether `gh` pages from the
oldest or newest end past ~100 comments. Real but low-probability (PR #690
itself, the extreme case, had 12 verdicts total): declined as a follow-up
probe rather than blocking this unit — fewer than 100 comments describes the
overwhelming majority of PRs this gate could ever run against.

## Architecture Review — not run separately, and why

Step 3.5/2a's second external call (`--mode architecture` over a
should-we-build-this-at-all brief) is intentionally NOT made in this run.
`project_architecture_review_run_order` records the exact failure mode this
would repeat: build had already completed (Step 6) before the Branch-A
`--mode iterate` plan-review call was even made — itself already retroactive
per that memory's own definition — so a second, architecture-scoped call
now would face the identical defeat-of-purpose the prior incident named:
"because the code was already built and reviewed, the reject could only
produce a reconciliation note declining to rearchitect, not a real course
change." The should-we-build-this question was, unusually, already settled
with explicit reasoning BEFORE any of this — the initiating brief itself
argued and rejected the one real alternative (a push-counter) with the same
rigor an architecture review would apply, before a single line was written
(see "Why not a push count" and "Alternative considered and rejected"
below). Running the call now would spend two more model calls to
re-arrive at a verdict already reasoned through, not to change course.
Recorded here rather than silently skipped, per the memory's own
"how to apply."

## Code Review (Stage 2) — findings and triage

`shipwright-build:code-reviewer` found 8 issues (2 medium, 6 low). Triaged:

**FIXED — Acceptance-B was non-discriminating (medium).** `test_two_genuinely_different_blocks_do_not_recur`
called `non_converging` with no `commits`/`head_sha`, so it always returned
`None` via the commit-binding fail-open path regardless of what the text
predicate decided — a regression in `findings_recur` would not have been
caught. Fixed: the test now supplies commit-binding data that WOULD satisfy
`verdicts_span_distinct_commits`, so only the text predicate can produce the
asserted `None`.

**DISCLOSED, not fixed — partial recurrence (medium).** See "DISCLOSED, not
fixed — the match fires on PARTIAL recurrence" above (added directly beside
the pre-existing threshold-calibration disclosure it sits next to in this
spec) — narrowing the predicate to require "no new findings" would have
broken the validated PR #690 acceptance case itself.

**FIXED — canary missed the bullet-format shape (low).** Added a fourth
assertion (`"\n- a.py:1 — x" in body`) to the renderer canary.

**FIXED — authenticity did not reject edited comments (low).** `is_authentic`
now also requires `not comment["includesCreatedEdit"]` — a write-access user
editing another author's comment is the same denial-of-delivery risk from a
higher-privileged actor; the field is already present in the payload this
reads, no extra `gh` call.

**FIXED — `_commit_as_of`'s docstring overclaimed exactness (low).** Rewritten
to state the binding is an approximation (nearest commit by timestamp, not
the actual reviewed head SHA) and name the one failure direction that is not
symmetric with the fail-open cases.

**FIXED — the new `gh` call site was untested for repo-pinning (low).** Added
an `argv`-pinning assertion to the acceptance end-to-end test, matching the
convention `test_deliver_pr.py:160-162` already established elsewhere.

**FIXED — dead fallback in `_run_ladder` (low).** `host = host or
Host.default(repo=repo)` was unreachable once `deliver()` started resolving
`host` up front (for the escalation call too); removed, parameter retyped
`Host` (not `Host | None`).

**FIXED — `PR_REVIEW_CHECK_NAME` duplicated `automerge_readiness`'s canonical
posted-status-context table (low).** Now imports
`POSTED_STATUS_CONTEXTS["pr-review-run.yml"]` from `lib.automerge_readiness`
instead of redefining the literal, so a workflow-check rename cannot silently
stop this escalation from firing without also breaking that module's own
drift test.

**FIXED — `_STOPWORDS`'s comment undersold its own contents (low).** Rewritten
to name both real categories (grammatical function words, plus
review-boilerplate verbs like "add"/"require(s)"/"tracking" that carry no
signal because every BLOCK claim shares them) instead of claiming "function
words only."

## Doubt Review (Stage 3) — findings and triage

`shipwright-build:doubt-reviewer` (MANDATORY for this unit — a TERMINAL,
one-way enforcement gate is exactly the "irreversible operation" class this
review exists for) found 5 doubts (2 high, 2 medium, 1 low). Triaged:

**FIXED — login-only authenticity is forgeable by another same-repo
workflow (HIGH #1).** This repo's own `pr_review_dismiss_select.py`
documents why login alone is not proof of origin — "every workflow in a
repository posts as `github-actions[bot]`" — and it is not hypothetical:
`bloat-check.yml` posts PR comments under the same login, built from
`_bb.scan()`'s file-path list with no character restriction, and `is_authentic`
plus `is_block_verdict` (unanchored substring checks) are everything a
maliciously-named file's path needs to satisfy. Verified live: `bloat-check`'s
real comment format (`### Added baseline entries` + backtick-quoted paths in
`- ` bullets) already matches the shape `is_block_verdict`/
`extract_blocking_findings` parse. Fixed structurally, not by pattern-matching
harder: `verdicts_span_distinct_commits` now requires each comment to
correlate to a sibling `CHANGES_REQUESTED` review (same bot login, unedited,
`submittedAt` within `_REVIEW_MATCH_WINDOW_SECONDS` of the comment) whenever
`reviews` data was fetched at all — `bloat-check.yml` never calls `gh pr
review`, so a forged comment has nothing to correlate to. This exploit still
needs write access to the repo (the same trust tier the code-review round's
edited-comment fix already accepts as residual risk), so it does not widen
the threat model to forks/external contributors — but it does close a gap in
that same tier using data already in reach.

**FIXED — commit binding used an inferior clock when an authoritative one
was available (HIGH #2).** `_commit_as_of` inferred a comment's commit from
`commits[]`/`committedDate` — an approximation with both failure directions:
a push landing mid-review makes a same-code stage-1 re-run look like "a
distinct, current commit" (false positive), and any rebase permanently
breaks the binding on that PR going forward (false negative), at exactly the
moment a long non-converging loop makes rebasing likely. `pr_review.py`'s
`_post_verdict` already posts a `CHANGES_REQUESTED` review alongside every
comment, and GitHub stamps that review's own `commit.oid` at submission — no
producer change needed, confirmed live: `gh pr view 690 --json reviews`
still returns both, `commit.oid` intact, `submittedAt` ~1 second after the
paired comment, even though #690's `commits[]` history is gone to the same
rebase. `verdicts_span_distinct_commits` now prefers this binding
(`reviews`), falling back to the `committedDate` approximation only when
`reviews` itself is empty (the fetch was not attempted or came back empty) —
never when it was fetched but this particular comment matched nothing in it,
which is what keeps the HIGH #1 fix structurally sound.

**DISCLOSED, not fixed — an intervening APPROVE does not reset the BLOCK
pair (MEDIUM #1).** `two_most_recent_block_verdicts` already documents this
choice deliberately: an approve/comment verdict between two BLOCKs "does not
reset the count... 'the last two BLOCKs agree' is still the right question to
ask." Doubt-reviewer's counter is real — a stale BLOCK from long before a
genuine, later APPROVE could still pair with a fresh, unrelated BLOCK,
discarding positive proof of non-stuckness. Declined for now: PR #690's own
12 verdicts contain no intervening APPROVE (all consecutive BLOCKs), so
there is no real-data case motivating the added complexity of tracking
"has this PR gone green since the previous BLOCK", and building it now,
untested against any real occurrence, risks the same kind of premature,
self-validating fixture the commit-binding fix just replaced. Revisit if a
future incident shows this actually firing.

**FIXED — spec overstated file-path-strictness and vocabulary-overlap as
independent (MEDIUM #2).** See the Threshold provenance disclosure above and
this file's own round-1/round-2 fixtures: review boilerplate ("add a test in
`shared/tests/test_x.py`") routinely supplies both a shared file path and
several shared tokens together, so the two are correlated in practice, not
independent mitigations layered for extra safety. This does not change the
predicate — a strict file match narrows WHERE the tokens have to overlap,
regardless of how they got correlated — but the spec should not claim more
independence than the real fixture shows.

**FIXED — `_commit_as_of` tie-broke by oid text, not commit order (LOW).**
Two commits sharing a `committedDate` now resolve to whichever the `commits[]`
array listed LAST (chronological order, per `gh pr view --json commits`) —
an oid's lexical value carried no ordering signal at all. Test:
`shared/tests/test_pr_review_verdict_provenance.py::test_committed_date_ties_break_by_array_order_not_oid_text`.

**DISCLOSED, not fixed — silent fail-open paths leave no operator-visible
trace, and `isMinimized` is unchecked (LOW).** Seven `None`/`False` returns
across this predicate carry no entry in `steps`/the result JSON, so an
operator cannot tell "the guard ran and found nothing" from "the guard could
not evaluate at all" — and a comment a human has manually minimized as
outdated is still eligible to be read as a current verdict. Both are real,
scoped observability/precision gaps, not correctness gaps: the operator still
sees the ordinary `checks_failed` (exit 2) message either way, since every
fail-open path's only effect is "do not escalate" — the case that was already
the caller's baseline behavior before this unit existed. Declined for this
unit: tracing seven distinct internal branches through to `steps` is a
moderate redesign of the return shape (a bool/dict is not enough; each path
would need its own reason code), and `isMinimized`'s absence from the current
`--json comments,commits,headRefOid,reviews` field list — GraphQL exposes it
on `IssueComment` — is one more field to thread through, both reasonable
follow-ups but outside this unit's TERMINAL-safety scope.

## Why not a push count

"Stop after N pushes" halts a run that is genuinely converging through a list
of distinct real findings — the good, common case. The signal that separates
that from a stuck run is SAMENESS, not volume: on PR #690 the sameness
predicate fires at round 2 (saves ~7h); a count of 5 fires at round 5 (saves
~3h) while still burning most of the wasted time on the common case's own
false positives (a run that legitimately needed 4 rounds would be cut short
by a count threshold tuned to catch #690 early).

## Scope guards (all four hard, per the brief)

1. The `PR Review` gate stays stateless per commit — `pr_review.py` and
   `.github/workflows/pr-review-run.yml` are untouched; nothing here reads
   from or writes to them. `lib.pr_review_convergence` is read-only from the OUTSIDE, after the
   gate has already failed twice.
2. Nothing here makes a review more lenient, blocks a merge that would
   otherwise pass, or changes any verdict — `escalate_if_non_converging` only
   ever replaces an existing `checks_failed` verdict with a stricter
   (`non_converging`) one; it never manufactures a failure the ladder had not
   already reported, and every other status passes through untouched (see
   Test Completeness Ledger row for the fail-open tests).
3. No new Required Check, no workflow change — `.github/workflows/*` is
   untouched by this diff.
4. The halt hands back to a human — F11's exit-8 arm is terminal, never
   auto-close/auto-draft/auto-revert; `deliver_pr.py` at exit 8 does NOT call
   `retire_run_pointer_best_effort` (that only fires on `EXIT_DELIVERED` /
   `EXIT_CLOSED`), so the run's F11 pointer and worktree stay live for the
   operator to return to.

## Threshold provenance (not invented, measured)

`MIN_SHARED_TOKENS = 4`, `MIN_CLAIM_OVERLAP = 0.2` (overlap coefficient:
`|shared| / min(|a|, |b|)`), tuned against PR #690's own round-1/round-2
comment BODIES (`shared/tests/_pr690_review_fixtures.py::ROUND1_BODY`/
`ROUND2_BODY` — the exact bytes `gh pr view 690 --repo svenroth-ai/shipwright
--json comments` returned, not paraphrased): they share 9 significant tokens
on an overlap coefficient of 0.32, both comfortably above the floor. The two
rounds' claims are worded completely differently (round 1: "make fingerprint
drift a decision-enforced condition"; round 2: "the fingerprint is not bound
to an authenticated CI result") but concern the same underlying
trust-boundary gap, and both name
`shared/scripts/tools/promote_required_layers.py` at different line ranges —
exactly the "loose on text, strict on location" shape the brief specifies.

**Disclosure — one fixture half is still synthetic; the other became real
mid-review.** Originally (spec-reviewer round 1) the commit oids/timestamps
the fixture module exports alongside the two real comment bodies were
entirely synthetic placeholders, because PR #690 had been rebased by an
unrelated concurrent session and its `commits[]` history from Sept 8 was no
longer reachable. Doubt-reviewer Stage 3 (HIGH #2) pointed at a source that
survives a rebase: `gh pr view 690 --json reviews` still returns each
review's GitHub-stamped `commit.oid`, because reviews are not commits and are
not rewritten by one. Re-fetched live during doubt triage, `round_reviews()`
now carries the REAL `commit.oid`s (`3f7beacff7...`, `1078c49151...`) and
`submittedAt` timestamps for PR #690's own round-1/round-2 reviews — and this
is now the PRIMARY binding path (`verdicts_span_distinct_commits` prefers
`reviews` over `commits[]`; see the Doubt Review section below). Only the
FALLBACK path — `commits[]`/`committedDate`, used when `reviews` itself comes
back empty — still rests on synthetic placeholder timestamps, for the same
now-narrower reason: #690's raw commit history is what the rebase actually
erased.
Acceptance-A (`test_pr690_round1_and_round2_recur`) now binds via the real
`reviews` fixture; the fallback-path tests in
`shared/tests/test_pr_review_verdict_provenance.py` are the ones still
exercising the synthetic half.

## Alternative considered and rejected

**A push counter (`stop after N`).** Rejected per "Why not a push count"
above — it is the wrong axis (volume vs. sameness) and the brief is explicit
that a count-based predicate would both fire too late on #690 and fire too
early on a genuinely converging run.

## Confidence Calibration

- **Boundaries touched:** the F11 delivery-ladder exit-code contract
  (`lib.pr_delivery`), a `gh`-backed I/O read (`host.call_json(["pr", "view",
  …, "comments"])` — new call site, existing `Host.call_json` seam, no new
  subprocess boundary), and the F11 skill-reference prose contract
  (`case "$?"`).
- **Empirical probes run:**
  1. Fetched PR #690's real round-1/round-2 `PR Review` BLOCK comments via
     `gh pr view 690 --repo svenroth-ai/shipwright --json comments` and
     measured the claim-overlap the matcher would compute — 9 shared tokens,
     0.32 overlap coefficient — BEFORE fixing the threshold constants, so the
     thresholds are set with margin below a real measurement, not guessed.
  2. Ran the full existing `deliver_pr`/`pr_delivery`/`pr_self_merge`/
     `pr_readiness`/`watch_pr_delivery` suite (179 tests) after wiring the
     escalation in — 0 regressions, including the two pre-existing
     `checks_failed` tests that use a non-`PR Review` check name (confirms
     the guard only reads the one gate it is allowed to).
  3. Ran the anti-ratchet gate (`anti_ratchet_check.py --staged`) against the
     staged diff — 0 (no ratchet) after bumping `deliver_pr.py`'s baseline
     `current` to the measured 340.
  4. (Doubt Review follow-up) Re-fetched PR #690 live a second time — `gh pr
     view 690 --repo svenroth-ai/shipwright --json reviews` — and confirmed
     each `CHANGES_REQUESTED` review's `commit.oid` and `submittedAt` are
     still intact and still line up (~1 second after the paired comment's
     `createdAt`) despite the intervening rebase that broke `commits[]` for
     the same PR — the empirical basis for preferring `reviews` as the
     binding source, not a design guess.
  5. Also verified live that `bloat-check.yml`'s real PR-comment format
     (`### Added baseline entries` + backtick file-path bullets) already
     matches the shape `is_block_verdict`/`extract_blocking_findings` parse —
     confirming HIGH #1's forgery path was concrete, not theoretical, before
     deciding it was worth fixing structurally.
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:** asymptote (depth) — the predicate is tested
  down to its failure-open edges (unreadable comments payload, a failing
  check that isn't `PR Review`, `reviews` empty vs. fetched-but-unmatched) and
  its true-positive edge (real #690 bytes AND real #690 review data), not just
  the sunny-day path. Coverage (breadth) — the pure predicate
  (`test_pr_review_convergence.py`, 20 tests: extraction, token
  normalisation, overlap arithmetic, the two acceptance fixtures), the
  provenance module's own tests (`test_pr_review_verdict_provenance.py`, 5
  tests: real-review binding, the forged-comment non-bind case, the
  empty-`reviews` fallback, the tie-break fix), and the ladder-integration
  surface (`test_deliver_pr_non_converging.py`, 5 tests: no-history,
  wrong-check-name, the acceptance escalation, a same-commit rerun,
  unreadable-comments fail-open) are all exercised. `cross_component` does
  not fire on this diff (none of
  `deliver_pr.py`/`pr_delivery.py`/`pr_self_merge.py` match
  `CROSS_COMPONENT_FILE_PATTERNS`), so no separate integration-coverage
  behavior is owed.

### Test Completeness Ledger

| # | Behavior | Status | Evidence |
|---|---|---|---|
| 1 | `extract_blocking_findings` reads only the `### Blocking issues` section, ignoring `### Comments` | tested | `test_extract_blocking_findings_reads_only_the_blocking_section` |
| 2 | A comment with no blocking section (approve) yields no findings | tested | `test_extract_blocking_findings_empty_on_approve` |
| 3 | `normalized_tokens` strips file paths, digits/line-ranges and stopwords, keeps domain nouns | tested | `test_normalized_tokens_strips_file_paths_digits_and_stopwords` |
| 4 | `claim_overlap` is 0 on disjoint vocabulary | tested | `test_claim_overlap_is_zero_on_no_shared_vocabulary` |
| 5 | `claim_overlap` uses the smaller claim's own vocabulary as the denominator | tested | `test_claim_overlap_uses_the_smaller_claims_own_vocabulary` |
| 6 | `findings_recur` requires the SAME file — no cross-file false match | tested | `test_findings_recur_requires_the_same_file` |
| 7 | `findings_recur` tolerates reworded claims on the same file (loose-on-text) | tested | `test_findings_recur_tolerates_reworded_claims_on_the_same_file` |
| 8 | `findings_recur` returns `None` when vocabulary genuinely differs on the same file | tested | `test_findings_recur_none_when_vocabulary_genuinely_differs` |
| 9 | `is_block_verdict` true only for a Shipwright `PR Review` BLOCK, not an approve or an unrelated comment | tested | `test_is_block_verdict_true_only_for_shipwright_block` |
| 10 | An APPROVE in between two BLOCKs does not reset the "last two BLOCKs" pair | tested | `test_two_most_recent_block_verdicts_ignores_non_block_comments_between` |
| 11 | Fewer than two BLOCK verdicts ⇒ `None` (nothing to recur against) | tested | `test_two_most_recent_block_verdicts_none_below_two` |
| 12 | **Acceptance A** — PR #690's real round-1/round-2 bytes recur on the shared file | tested | `test_pr690_round1_and_round2_recur` (real fixture, not paraphrased) |
| 13 | **Acceptance B** — two real-shaped BLOCK verdicts with genuinely distinct findings do NOT recur | tested | `test_two_genuinely_different_blocks_do_not_recur` |
| 14 | A single BLOCK verdict (no history) does not escalate | tested | `test_non_converging_none_on_a_single_block` |
| 15 | A BLOCK comment with no parseable blocking section does not escalate | tested | `test_non_converging_none_when_a_block_has_no_parseable_blocking_section` |
| 16 | End-to-end: a red `PR Review` check with only ONE prior BLOCK stays `checks_failed`/exit 2 | tested | `test_a_red_pr_review_check_with_no_history_still_reports_checks_failed` |
| 17 | End-to-end: a failing check that is NOT `PR Review` never triggers a comments fetch (scope guard 1) | tested | `test_a_failing_check_other_than_pr_review_never_asks_for_comments` |
| 18 | End-to-end: two recurring `PR Review` BLOCKs (PR #690 bytes) escalate to `non_converging`/exit 8 through the full ladder | tested | `test_two_recurring_pr_review_blocks_escalate_to_non_converging` |
| 19 | End-to-end: an unreadable comments payload fails OPEN to `checks_failed` (never manufactures a halt, never swallows the real verdict) | tested | `test_an_unreadable_comments_list_fails_open_to_checks_failed` |
| 20 | `summary()` renders both verdicts side by side with a `STOP` instruction for `non_converging` | tested | `test_non_converging_summary_quotes_both_verdicts_side_by_side` |
| 21 | Every pre-existing `deliver_pr`/`pr_delivery`/`pr_self_merge`/`pr_readiness`/`watch_pr_delivery` behavior is unaffected | tested | full suite re-run, 179/179 green, 0 changed assertions |
| 22 | A BLOCK-shaped comment from a non-bot author is ignored, even sharing file+claim with a real BLOCK | tested | `test_non_converging_ignores_forged_non_bot_comments` |
| 23 | Two BLOCK verdicts binding to the SAME commit do not recur (stage-1 re-run, not a re-push) | tested | `test_non_converging_none_when_verdicts_share_the_same_commit`, `test_a_same_commit_rerun_does_not_escalate` (end-to-end) |
| 24 | The current verdict must bind to the PR's actual head — a stale verdict does not escalate | tested | `test_non_converging_none_when_current_verdict_is_stale` |
| 25 | With no `commits`/`head_sha` supplied, the predicate fails OPEN rather than trust the text match alone | tested | `test_non_converging_fails_open_without_commit_binding_data` |
| 26 | The four literals/shapes this predicate depends on (`render_comment`'s marker, badge, heading, and bullet form) are pinned in the producer's own test root | tested | `test_block_verdict_marker_and_heading_are_the_literals_convergence_depends_on` |
| 27 | An edited comment (`includesCreatedEdit`) from the real bot login is not authentic, even with the right author | tested | `test_non_converging_ignores_edited_comments_even_from_the_real_bot` |
| 28 | The new `comments,commits,headRefOid,reviews` fetch is repo-pinned, matching every other `gh` call | tested | `test_two_recurring_pr_review_blocks_escalate_to_non_converging`'s `argv` assertions |
| 29 | PR #690's real `reviews` bind round-1/round-2 via `commit.oid` (not `committedDate`) — the primary path | tested | `test_real_pr690_pair_binds_via_review_commit_oid_not_committed_date` |
| 30 | A BLOCK-shaped comment with the real bot login, unedited, but NO sibling review near its timestamp does not bind (closes the login-only forgery gap, HIGH #1) | tested | `test_forged_comment_with_no_sibling_review_does_not_bind` |
| 31 | Once `reviews` was fetched at all, an unmatched comment does NOT fall back to the `commits[]` guess | tested | `test_reviews_present_but_empty_match_does_not_fall_back_to_commits` |
| 32 | `reviews=()` (fetch came back empty) still binds via the original `committedDate` approximation — fallback regression guard | tested | `test_empty_reviews_falls_back_to_committed_date_binding` |
| 33 | `_commit_as_of` ties resolve by array order, not oid text | tested | `test_committed_date_ties_break_by_array_order_not_oid_text` |

0 untested-testable. 33/33 rows `tested`.

## Verification (medium+)

- **Surface:** none (a CLI/library change to a pipeline delivery tool has no
  browser or running-app surface to drive) — `justification`: this changes
  `deliver_pr.py`'s internal decision logic and a documentation reference
  file; there is no `dev_url`, no UI, and no running service this diff
  affects. F0.5 records `surface: none` with this justification per the
  matrix ("Advisory at trivial" / opt-out path for a non-UI backend change).
- **Runner:** n/a (surface is none)
- **Evidence path:** `shared/tests/test_pr_review_convergence.py`,
  `shared/tests/test_pr_review_verdict_provenance.py`,
  `shared/tests/test_deliver_pr_non_converging.py`,
  `shared/tests/test_deliver_pr_summary.py`,
  `plugins/shipwright-security/tests/test_pr_review_render_convergence_canary.py`
