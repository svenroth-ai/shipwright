# Bloat exception — `shared/tests/test_campaign_step_3f_bis.py` raised to 540-LOC

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r3-review-diff-fix`
  (campaign-dag-scheduler R3, round 5). This test file was split out of
  `test_campaign_review_contract_prose.py` (which itself hit the same
  300-line limit) with no baseline entry filed at the time — a genuine
  omission caught by a fresh code-reviewer's round-4-verify pass (finding
  N5), not a deliberate decision to skip it. By that point five rounds of
  review-driven fixes to `campaign-mode.md`'s 3f-bis step had each added
  their own mutation-probed regression test here, crossing 300 lines
  without anyone re-checking this file's own budget.

## Context

`test_campaign_step_3f_bis.py` is the prose-contract test suite for loop
step `3f-bis` (the delegated review cascade) and its unit-scoped
review-attribution machinery, added by R3. Each of five review rounds on
this sub-iterate (spec-review rounds 1/2/4/5, code-review rounds
3/4/4-verify/5) found a genuine defect in `campaign-mode.md`'s 3f-bis text
and each fix shipped with its own mutation-probed test in this file, per
this repo's own stated convention ("Each guard here has been
mutation-probed: delete its subject from the step and it fails" — this
file's own module docstring). The file is now 540 lines against the
300-line default.

## Ousterhout Argument

This file is a deep module by the same measure `campaign-mode.md`'s own
bloat exception uses: a narrow, stable interface (`_step_3f_bis()`/
`_step_3g()` from `_campaign_prose_harness.py`, returning one normalized
string) hides substantial behavior — one assertion per named hazard this
sub-iterate's five review rounds found, each anchored on the literal
command form so a regression is caught by deleting the code it guards,
not by re-reading prose. Splitting it by hazard category (worktree
resolution vs. spawn-boundary survival vs. cascade ordering) would
fragment tests that share the same harness call and the same underlying
step body, without shrinking the actual assertion count or the review
history each docstring records.

## YAGNI Check

- Every test in this file guards a hazard an actual review round found in
  the live `campaign-mode.md` text — none are speculative or exercise
  behavior nobody asked for. Deleting any one test (confirmed by
  mutation-probing the newest ones, this round) lets a real regression
  back in.
- The review-round provenance in each docstring ("spec-review round 2:
  ...", "code-review round 4, medium: ...") is not decorative: it is what
  lets a future reader tell a still-load-bearing guard from one whose
  underlying code has since been refactored away, and it is the same
  convention this campaign's other bloat-exception ADRs already use for
  `campaign-mode.md` itself. Trimming it purely to shrink line count would
  remove the one thing that makes each assertion auditable independently
  of this ADR.
- No responsibility here is preparatory or forward-looking: every
  assertion targets code that exists in `campaign-mode.md` today.

## Chesterton-Fence Check

The fence here is the file's own history: it was split out of
`test_campaign_review_contract_prose.py` specifically because that file's
own bloat exception was rejected in favor of a topical split (see this
file's own module docstring, "The split itself is a bloat split"). Re-
splitting `test_campaign_step_3f_bis.py` again now, along some other seam,
would repeat the same churn one review cycle later once R4/R5a add their
own 3f-bis/3g tests here — the file's own "Consequences" note in
`campaign-mode.md`'s sibling bloat exception already anticipates this
("`campaign-mode.md` may grow again for R4 ... or R5a ... likely to touch
3f-bis/3g again"). The fence stands for a documented reason; it is not
being torn down.

## Decision

`current` is raised to 540 for `shared/tests/test_campaign_step_3f_bis.py`
in `shipwright_bloat_baseline.json` (`state: "exception"`, this ADR). The
deliberate retirement plan: this campaign's own R4 (state mechanics) and
R5a (wave-build flip) are both expected to touch 3f-bis/3g again per
`campaign-mode.md`'s own bloat-exception ADR; the Re-Review-Date
(2026-12-22) is the checkpoint to ask whether the accumulated review-round
provenance in this file's docstrings can be collapsed into references to
this ADR's own history instead of being repeated inline, the same
consolidation opportunity `campaign-mode.md`'s own exception recorded as
non-blocking (N6) rather than done immediately in round 5.

## Consequences

No downstream consumer reads this file except pytest itself and the
bloat-baseline gate this ADR is granting an exception against — it is not
imported by production code or other tests. The cost of the exception
holding past Re-Review-Date is purely readability: more provenance prose
to read before finding the assertion that matters. If R4/R5a add further
3f-bis/3g coverage here without a docstring trim, the next reviewer to
touch this file should raise `current` again with a one-line addendum
here, per this ADR's own established convention (see `campaign-mode.md`'s
sibling exception's four appended "Post-merge-cycle growth" sections).

## Rejected alternatives

- **Trim the review-round provenance out of each docstring now, to get
  back under 300 lines.** Rejected for this round: the reviewer that
  raised this finding (N5) explicitly estimated ~120 removable lines with
  zero assertions touched, but that trim alone would land at ~420 lines —
  still over budget — and doing a partial trim under time pressure, mid a
  five-round review cycle already converging, risks removing the exact
  provenance a NEXT reviewer needs to tell which hazard a given assertion
  guards. Deferred to the Re-Review-Date instead of rushed here.
- **Split the file again by hazard category** (worktree resolution /
  spawn-boundary survival / cascade ordering). Rejected: see Chesterton-
  Fence Check above — this file was already produced by exactly one such
  split, and R4/R5a are expected to add more tests to this same subject
  before the split would even stabilize.
- **Leave the crossing un-allowlisted and revert the round-5 test
  additions.** Rejected: three of this round's five review findings (the
  `fires` empty-file bug, the `run_dir` re-derivation gap, and the
  `pr_json` boundary loss) are real, currently-shipping defects in
  `campaign-mode.md` with no other regression coverage; reverting their
  tests to fit under budget would re-open exactly the bugs this round
  fixed.

---

## External Sources Acknowledged

This template's YAGNI Check + Chesterton-Fence Check headings are
adapted from:

- obra/superpowers, skill `writing-plans` —
  https://github.com/obra/superpowers — MIT © Jesse Vincent
- addyosmani/agent-skills, skill `code-simplification` —
  https://github.com/addyosmani/agent-skills — MIT © Addy Osmani

The Incident-Reference field follows the **pattern** of the per-decision
incident-reference convention in `multica-ai/multica` `CLAUDE.md`
(Apache-2.0 modified-with-hosting-restriction — patterns reusable, text
not copied).
