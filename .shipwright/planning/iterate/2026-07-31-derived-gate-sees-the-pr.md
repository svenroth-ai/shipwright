# The gate sees what the branch contributed, not what the tip commit touched

**Run-ID:** `iterate-2026-07-30-derived-gate-sees-the-pr`
**Type:** bug · **Complexity:** medium
**Closes:** `trg-815ad30a`

## The defect

`check_no_derived_snapshots_committed` is an ERROR-severity F11 gate: eleven shared
derived-view paths must not enter an iterate commit. It has been reporting
`none derived` while those files landed on `main`.

F11 runs `ensure_current` (integrate-if-behind) **before** the verifier, then hands the
verifier `--commit "$(git rev-parse HEAD)"`. If that integrate made a merge commit,
HEAD *is* the merge — and the gate inspected one commit. A merge commit's changed-path
set does not contain what the iterate's own commit carried.

Measured on PR #493:

| commit | paths seen | forbidden |
|---|---|---|
| `f5f6cca2` — the merge (what F11 inspected) | 5 | **0** |
| `48ee9665` — the iterate commit below it | 46 | **11** |

Eight of `main`'s last forty commits carry a forbidden derived path; **five landed
after the gate went live** (`24a56158`, `bebdc9a3`, `d9bc7d90`, `80647cc9`,
`23329f57`).

**This is the root cause of a chain.** It is why `shipwright_test_results.json` still
moves on `main`, which falsified the premise behind the run-written carve-out and
forced the byte-carry mechanism in PR #502. The gate has been the hole all along.

It is also easy to miss: when `ensure_current` reports `already-current` no merge
commit exists, the gate inspects the real commit and works perfectly. It goes blind
only when the branch was behind — the common case on a busy trunk, and exactly when
the churn matters.

## What changed

**The repo already had the answer.** `integration_coverage._iterate_changed_paths`
did merge-base..commit, with this rationale in its own docstring. One verifier had
solved it; the others never got it. So it MOVED to `verifiers/git_helpers.py` and four
gates now share it, rather than a fifth variant being invented.

**Naming the trunk is the part that goes wrong.** A stale `origin/master` after an
upstream rename still *resolves* — verifying resolvability is not enough. Candidates
are therefore SCORED: take each merge-base, keep the one all the others are ancestors
of. That is the narrowest honest range, and it is right for both the stale-symref and
the rewound-trunk case without telling them apart. More candidates is strictly safer
here, because the loop keeps the narrowest — an extra candidate can only pull the base
closer, never widen it.

**An empty answer is never clean.** The helper returns `None` (not `[]`) when the
merge-base view was unavailable and the single-commit fallback said nothing — on a
merge commit that fallback always says nothing. Callers already treat `None` as
unavailable, so all four gates are fixed at once instead of each re-deriving the
distinction. `[]` from the merge-base path stays trustworthy: no net change.

**A commit already contained in the trunk** has no range to measure, so it falls back
to the commit view — a stray `git add -A` straight onto `main` is still caught.

## Acceptance criteria

- (E) Given a forbidden path in an earlier commit with an `ensure_current` merge on
  top, when the gate runs on HEAD, then it fails and names the path.
- (E) Given mainline carried a derived path in through the merge, when the gate runs,
  then the branch is not blamed for it.
- (E) Given no resolvable base and a merge HEAD, when the gate runs, then it reports
  SKIPPED — never clean.
- (E) Given a branch whose net diff is genuinely empty, when the gate runs, then it
  passes rather than skipping.
- (E) Given a stale-but-resolvable `origin/HEAD` — including as the ONLY candidate —
  when the base is resolved, then the narrowest base wins.
- (E) Given a wedged repository, when a probe times out, then the ordering answer is
  not silently read as "not an ancestor".

## Review

Three stages plus the earlier findings folded in. Each stage found a real defect in
code the previous one had passed:

- **spec-reviewer** — REJECTED twice. I broke an existing test with the move and
  reported green after running two files instead of the root; and the first fix left a
  back door where the fallback still returned a false clean.
- **code-reviewer** — HIGH: the resolver I promoted to canonical for five gates was the
  weakest of five copies in the repo.
- **doubt-reviewer** — HIGH: the scoring is vacuous with a single candidate (`all([])`
  is True), which is exactly the shape of the motivating bug; plus `ci_supplychain`
  conflating `[]` with `None`, and a test that ran through a different path than its
  name claimed.

Both halves carry negative controls: reverting to the single-commit view fails three
tests, and narrowing the candidate pool fails the lone-candidate test.

**Filed, not fixed here:** `trg-d0e4592e` — the gate's printed remedy
(`--source=HEAD~1`) is a no-op on a merge HEAD, because `HEAD~1` is the commit that
carries the offender. Pre-existing; a different subject (what the gate SAYS, not what
it SEES).
