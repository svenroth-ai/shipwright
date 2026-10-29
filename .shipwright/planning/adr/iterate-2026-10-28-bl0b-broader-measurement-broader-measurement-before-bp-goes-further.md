# BL0b: measure BP on a broader base before it goes further

Unit BL0b of campaign `baseline-protection`. Binding source: `.shipwright/planning/campaigns/2026-10-27-baseline-protection-BRIEF.md`; result: `.shipwright/planning/campaigns/2026-10-27-baseline-protection-BL0B.md` and `.json`.

## Decision

Before BL1/BL2, measure BP against independent ground truth (two blind labelers) instead of the authors' own `affected_frs`: one HEAD context run of all 18 test roots mapped to the 100 historical PRs by qualified name, a path-ownership null model, new-code classes, AC level, 50 blind mutation probes and 35 blind label packs. The five decision rules were fixed before measuring and are evaluated unchanged. Nothing gates; no workflow, hook or CI file changes.

## Result

R-benefit PASS (3 confirmed undeclared changes, found by the git leg), R-recall PASS (21 of 27, interval 59-89 %), R-T-code-value FAIL (git + T-code is 15 points below git + path), R-precision FAIL, R-cost FAIL (43 of 100 PRs held at declared scope). Recommendation: SHADOW-ONLY.

## Architecture Review, plan review and code review

Not run by the runner: the coordinator reserved the review cascade for after hand-back; the rows are recorded `not_run` / `delegated-to-orchestrator` in `reviews.json`.

## Consequences

The operator decides at stop 1 whether BP continues, with BL1 and a git-leg-only shadow as the cheap next step; BL2 (T-code in CI) is not supported by this evidence.
