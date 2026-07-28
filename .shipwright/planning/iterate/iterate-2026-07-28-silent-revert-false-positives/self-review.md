# Self-review — iterate-2026-07-28-silent-revert-false-positives

Seven-point checklist, run on the final tree after all three cascade stages and
the external code review had been applied.

**1. Does it do what the spec says, and only that?** Yes. Three proofs plus the
ref repair, the doc update and the FR-01.11 fold. One scope judgement is
disclosed rather than smuggled: the default-ref resolution was *not* in the
original bug report (which is about false positives) — it is a false *negative*.
It is in scope because the case-(A) proof asks "does the default branch still
carry this?", and a stale ref answers that against the wrong tree. Measured
before deciding: 6 → 2 → 1 integration merges seen as the ref is walked back.

**2. Tests: would each fail without the change?** The ones asserting new silence
(AC1, AC1b, AC2, AC5) fail against the pre-change code. The ones asserting
continued noise (AC3, AC4, AC4b–AC4e) pass against pre-change code by
construction — that is correct for negative guards, and each is instead
mutation-sensitive against the delivered implementation: remove the base guard →
AC3 fails; remove the `p1` guard → AC4c fails; drop `-w` → AC4d fails; drop the
"and followed" condition → AC4e fails. Stated explicitly because "my test passes"
is not evidence for a guard.

**3. Failure modes.** Every filter can only REMOVE findings, so every git read
they depend on is fail-honest: `read_side` distinguishes absent from unreadable
on all four sides, records the reason, and the check reports findings *with* the
incomplete comparison rather than replacing them with a non-blocking SKIP. One
residual, checked by hand: an unreadable `p1` shrinks the exclusion set, which is
the *unsafe* direction (more suppression) — but it also appends a problem, so if
the suppression empties the findings the run returns a visible SKIP, never a
green pass.

**4. Did I weaken anything to make it pass?** No. The 16 pre-existing tests are
byte-identical to HEAD (`git diff` empty) and green. The motivating failure was
re-verified at real scale on a real 2,700-line file: still blocks, 185 lines.

**5. Accepted risks, written down rather than implied.**
- Token containment proves words survive, not meaning. Bounded on three sides and
  pinned by `test_the_accepted_blind_spot_is_pinned_not_implied`.
- `-w` makes the hunks whitespace-insensitive while lines are compared after
  `.strip()`. A line whose *internal* whitespace changed is therefore a finding
  that no hunk can pair — a false positive, i.e. the safe direction. Not
  normalised away, because that would be a late broad behaviour change to what
  "the same line" means for the whole detector.
- `CHURN_ALLOWLIST` membership only, where `churn_merge.classify` also treats
  campaign `status.json` as churn. Pre-existing, unchanged, filed.

**6. Simplifications applied during review.** `merely_edited` → `unexplained_by_edit`
(its polarity was the opposite of its sibling's, called back-to-back — an
inversion hazard on a safety gate). One `file_lines` instead of two. Replacements
tokenised once per hunk instead of once per pair. And the two hunk caches were
sharing one dict with different key shapes (`path` vs `(delivered, path)`) —
safe, since a str can never equal a tuple, but it read as a bug; now two named
dicts.

**7. Affected Boundaries.** `verifiers/silent_revert.py` (detector, F11 entry
point, unchanged signature), the two new sibling modules, and read-only git.
`shipwright_test_results.json → iterate_latest.declared_removals` keeps its shape
— the point of the change is that it stops being needed. No config, env var,
hook or workflow. Three modules where #477 had one: forced by the repo's own
300-line cap, disclosed in the mini-plan, and each file is now under it
(299/174/201).
