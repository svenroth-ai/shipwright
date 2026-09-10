# Nothing-to-review carve-out for the PR-review gate

## Context

PRs #707 and #708 (Actions runs 34478538161, 34483979873) both posted
`PR Review = failure — "review blocked or did not complete"` even though
every changed path was a producer-generated artifact (compliance docs,
`.shipwright/triage.jsonl`) with zero reviewable content — the delivery
path documented in `shared/scripts/tools/refresh_compliance_docs.py:1-18`.
Two individually-correct rules composed into a wrong outcome: the
generated-path filter (hides regenerated content from the model's diff)
and stage 2's fail-closed default (`pr-review-run.yml`'s own header
comment) never distinguished "nothing to review" from "review failed",
so a fully-generated PR fell through the fail-closed branch every time
and forced a `gh pr merge --admin` override.

## Decision

Stage 2 (default-branch, contributor-uneditable code — never stage 1's
artifact, the FR-01.17 (E)7 self-exemption this repo has caught once
before) derives a new `all_generated`/`all_generated_reason` classification
from the trusted API-read changed-path list. It uses a new,
**strictly narrower** classifier, `pr_review_generated.is_safe_to_skip_review`
— not the existing `is_generated_path`, which is deliberately broader for
its own lower-stakes job of hiding content from the model's reviewed diff
— because deciding whether the gate may be skipped ENTIRELY is a
higher-stakes decision than deciding what the model sees. It excludes the
three agent-instruction docs (`_GENERATED_AGENT_DOCS`) that `is_generated_path`
still treats as generated, and anchors basename-only matches to their
canonical paths so e.g. `plugins/x/shipwright_test_results.json` off its
real producer directory is not skip-safe.

`review_record_tier.classify_generated_only` composes this classifier with
the existing `SENSITIVE_PATH_RE`: any sensitive path anywhere in the diff
(`.github/workflows/**`, `scripts/ci/**`, etc.) forces `all_generated=False`
regardless of how many generated paths sit next to it (hard constraint 2).

The final `(state, description)` verdict is now composed by one new pure
function, `lib/pr_review_gate_verdict.decide_gate`, replacing the inline
bash `if/elif/fi` block. It is the single seam where every upstream signal
(stage-1 success, the tier decision, `all_generated`, the waiver, and the
review step's actual outcome) becomes the posted commit status. The
`all_generated` branch only short-circuits to `success` when the review
step's outcome shows it never actually ran (`""` or `skipped`) — if the
review step ran anyway and failed, that failure wins unconditionally
(hard constraint 4: this narrows one specific case, it does not become a
catch-all). A waiver-consumption failure also wins over the carve-out,
because a PR whose only changed path is a corroborated review-record file
can be `all_generated=True` and `needs_review=False` at the same time.

`PR Review` keeps exactly one producer — stage 2's existing verdict step
(hard constraint 3); no second workflow or job emits that context.

## Consequences

An all-generated PR now posts `PR Review = success` with a self-explaining
description instead of forcing an admin-override merge every time. The
decision logic moved out of inline workflow bash into two tested pure
Python functions (`classify_generated_only`, `decide_gate`), each with its
own unit-test module, so the composition is reviewable and pinned instead
of drifting silently inside YAML nobody diffs for logic changes. The
workflow's "Run Tier-3 PR review" step gained a third `if:` condition
(`steps.tier.outputs.all_generated != 'true'`) alongside the two
pre-existing ones.

## Rationale

Deriving the classification in stage-2 default-branch code (not from
stage 1's artifact) keeps the trust boundary FR-01.17 (E)7 requires: a
contributor cannot edit the code that decides whether their own PR needs
review. Keeping the classifier strictly narrower than the existing
generated-path filter avoids reusing a policy that was tuned for a
different, lower-stakes decision. Composing the verdict as one pure
function (rather than more inline bash) makes the exact precedence
(stage1 > tier > waiver > all_generated > review outcome > waiver-success)
testable and prevents a future edit from silently reordering it.

## Rejected alternatives

- **Read the "nothing to review" signal from stage 1's own artifact** —
  rejected outright: this is precisely the self-exemption FR-01.17 (E)7
  forbids (a contributor's own PR code deciding whether it needs review),
  already caught once in this repo's history
  (iterate-2026-07-27-pr-review-forged-boundary lineage).
- **Reuse `is_generated_path` directly for the skip-review decision** —
  rejected: it is deliberately broader (includes agent-instruction docs,
  matches generated basenames anywhere in the tree) because its job is
  hiding content from the model's diff, a lower-stakes decision than
  skipping the review gate entirely. A doubt-review pass confirmed this
  would have let an off-canonical-path or an agent-instruction-doc-only
  PR skip review incorrectly.
- **A catch-all "if the diff looks generated, always pass"** — rejected:
  hard constraint 4 requires a crash, cancellation, missing secret, or
  empty model response to still fail. The chosen design only short-circuits
  when the review step structurally never ran (gated by the same `if:`
  condition), and defends against it anyway if that gating is ever loosened
  in a future edit — verified by `test_model_api_failure_on_an_all_generated_pr_still_fails`.

## Test coverage

- `test_pr_review_gate_verdict.py::test_all_generated_pr_posts_success_with_the_naming_description`
  — acceptance 1 (all-generated → `success`, naming description).
- `test_pr_review_gate_verdict.py::test_a_sensitive_path_in_the_mix_means_all_generated_is_false_upstream`
  — acceptance 2 (one sensitive path still blocks).
- `test_pr_review_gate_verdict.py::test_model_api_failure_on_an_all_generated_pr_still_fails`
  — acceptance 3 (a model/API failure on an all-generated PR still fails).
- `test_review_record_tier.py`, `test_pr_review_generated_skip_review.py` —
  classifier unit coverage, including the doubt-review regressions (agent
  docs not skip-safe; off-canonical basenames not skip-safe).
- `test_pr_review_generated_only_gate_shape.py` — workflow-shape assertions
  (the three-condition `if:`, the `set -e` crash-safety guard around the
  gate-decision script call).

See `.shipwright/planning/iterate/iterate-2026-09-10-pr-review-generated-only.md`
for the full iterate spec, confidence calibration, test completeness ledger,
and review-cascade findings (code review, doubt review, external review).
