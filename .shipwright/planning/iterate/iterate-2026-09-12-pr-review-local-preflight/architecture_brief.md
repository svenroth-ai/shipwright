# Architecture Brief: local PR-review preflight

## The problem

The required Tier-3 PR-review gate reviews against a threat model, a
different question from the spec-compliance cascade already run before
every push. That cascade's green result therefore carries no information
about the CI gate's verdict, and every finding the gate has ever made costs
a full push → CI → review round to learn — three times in one day
(2026-09-12), each a real defect the gate correctly caught, none caught any
earlier in the pipeline.

## What already exists here

- `scripts/verify_local.py` — mirrors CI's bespoke merge guards; runs at F0
  and again at F11 before push.
- The spec-compliance review cascade (`spec-reviewer` → `code-reviewer` →
  `doubt-reviewer`, Step 8) — reviews the diff against the iterate's OWN
  plan, before F6 commits it.
- The required CI `PR Review` gate (`pr_review.py`, stage 2 of FR-01.17) —
  reviews the pushed PR's diff against a threat model; the sole authority
  for the required check.

## What would newly, permanently exist

A second invocation path for `pr_review.py`: local-diff sourcing
(`--base`/`--diff-file`) alongside the existing CI-only `--pr-number`/
`--repo` path, plus one new mandatory-but-advisory step in the F11
finalization flow that calls it before every medium+ push. From now on this
tool has two callers to keep in sync (CI's stage-2 workflow, and F11), one
new argument-validation surface, and one new "what if the LLM call itself
fails" case F11 must keep answering correctly (advisory, not blocking).

## Options on the table

- **A:** Add `--base`/`--diff-file` to `pr_review.py` itself, sharing
  every prompt/model/filter/decision code path with CI mode; wire a new
  advisory step into F11 before push.
- **B:** A separate, standalone script that duplicates the review logic
  (prompt loading, OpenRouter call, decision parsing) rather than extending
  `pr_review.py`.
- **C:** Do nothing; rely on the spec-compliance cascade plus the required
  CI gate as today, accepting the push→CI→review round trip as the
  discovery latency for this class of finding.

## Constraints that are not negotiable

- The local run must be structurally incapable of satisfying the required
  CI gate — no artifact it writes may be read by `review_record_tier.decide()`.
- No side effects in local mode: no PR comment, no review state, no
  dismissal of a stale verdict.
- Same prompt directory, model, and generated-file filter as CI, or the two
  verdicts are not comparable.
- Diff against the merge base, never the branch tip of `origin/<default>`.
- Untracked files must be included — the three real 2026-09-12 findings all
  lived in files of exactly that class.
