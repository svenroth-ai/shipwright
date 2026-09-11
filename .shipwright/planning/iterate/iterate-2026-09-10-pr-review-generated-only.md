# Iterate: PR-review gate posts success for all-generated PRs

- **Run ID:** iterate-2026-09-10-pr-review-generated-only
- **Type:** CHANGE
- **Complexity:** medium (self-escalated from the classifier's `small` — the
  diff touches `.github/workflows/pr-review-run.yml` (`touches_ci_supplychain`,
  min `small`), and the required composition + classification logic spans
  three new/changed modules plus their tests, which warrants the fuller
  process — spec, confidence calibration, mandatory review).
- **Spec Impact:** NONE (no FR change — this fixes a gate's own decision logic,
  not application requirements).

## Problem

Observed twice in one hour (2026-09-10) on two different delivery paths: PR
#707 (`refresh_compliance_docs.py --pr` output — 7 compliance artifacts) and PR
#708 (triage-card delivery — `.shipwright/triage.jsonl`). Both posted `PR
Review = failure — "review blocked or did not complete"` with all 11 other
required checks green, because `pr_review.py` filtered every changed path as
generated (no reviewable logic) and then correctly refused to call that a
review — "everything was generated" is not a review, so it fails closed
(`plugins/shipwright-security/scripts/tools/pr_review.py:188-211`).

Two individually-correct rules compose into a wrong outcome: the generated-path
filter is right (no reviewable logic, would blow the size cap), and the
fail-closed rule is right (an absent status must never read as passing,
FR-01.17 (E)2/(E)7). But an empty review set (nothing here for a reviewer to
judge) is a *complete* review with zero findings, not a *failed* one — and
conflating them forces a `gh pr merge --admin` override on every regenerated
compliance-doc PR and every triage-card PR, both of which are designed,
on-demand delivery paths through a human-reviewed PR
(`refresh_compliance_docs.py:1-18`). P3.5's promotion needs main's manifest
drift-clean, so this is about to get more frequent, not less.

## Fix

Derive "nothing to review" in **stage 2** (`pr-review-run.yml`), from the
trusted API-read changed-path list, in default-branch code the contributor
cannot edit — never from stage 1's artifact (that is precisely the
self-exemption FR-01.17 (E)7 forbids, caught once already in this same
workflow's history).

- `review_record_tier.classify_generated_only(changed_paths)` — true iff every
  changed path is `pr_review_generated.is_safe_to_skip_review` **and** none
  matches `SENSITIVE_PATH_RE`. Emitted as new tier-step outputs
  `all_generated` / `all_generated_reason`.
  `is_safe_to_skip_review` is a NEW function, deliberately narrower than the
  pre-existing `is_generated_path` (which only hides a section from a model
  that still reviews the rest of the diff — lower stakes than letting the
  gate itself skip review). Added mid-iterate after a Stage-3 doubt review
  found that reusing `is_generated_path` wholesale let a PR touching only
  `.shipwright/agent_docs/{build_dashboard,session_handoff,triage_inbox}.md`
  (agent-instruction-surface files this repo reads back as agent context)
  skip review entirely, and that the basename-only matches
  (`triage.jsonl`/`shipwright_events.jsonl`/etc.) were not anchored to their
  canonical repo-root path — see "Doubt review findings" below.
- The "Run Tier-3 PR review" step's `if:` gains `&& all_generated != 'true'` —
  no OpenRouter call over content nobody wrote.
- The final verdict composition moved out of inline bash into a tested pure
  function, `pr_review_gate_verdict.decide_gate` (invoked via
  `decide_pr_review_gate.py`): when `all_generated` is true *and the review
  step never actually ran*, post `success` naming why (e.g. "no reviewable
  content - all 7 paths are generated artifacts"). If the review step ran
  anyway and failed, that failure still wins — the carve-out is narrow by
  construction, not a catch-all.

### Hard constraints honoured

1. Classifier lives in default-branch code, applied in stage 2 — never reads
   stage 1's artifact.
2. A sensitive path (`.github/workflows/**`, `shared/scripts/lib/**`, etc. —
   the existing `SENSITIVE_PATH_RE`) anywhere in the diff still blocks the
   carve-out and forces review, regardless of how many generated paths sit
   next to it.
3. `PR Review` keeps exactly one producer — same workflow, same final step,
   same posted status.
4. A crash, cancellation, missing secret, or empty model response still
   fails — `decide_gate`'s `all_generated` branch only fires when the review
   step's outcome is empty/`skipped` (i.e. it structurally never ran); a
   `failure`/`cancelled`/`timed_out` outcome falls through unchanged.

## Confidence Calibration

- **Boundaries touched:** the `.github/workflows/pr-review-run.yml` CI trust
  boundary (io boundary: workflow step outputs/env passed as CLI args across a
  process boundary); no application code, no runtime request path.
- **Empirical probes run:**
  - Full `shipwright-security` plugin suite: 1008 passed, 7 skipped (pre-existing
    skips, unrelated — gitleaks/oss-backend smoke tests needing external
    binaries).
  - Lint (`uvx ruff@0.15.15 check`) on every new/changed file: clean.
  - `shared/tests/` full run (includes `test_pr_review_fail_closed.py` and
    `test_pr_review_fork_trust.py`, which parametrize over both this repo's
    stage-2 workflow and the shipped adopt-target template — the template is
    untouched and out of scope, a simpler no-tier/no-waiver starter gate).
- **Test Completeness Ledger:** see below.
- **Confidence-pattern check:**
  - *Asymptote (depth):* `decide_gate` is tested at every branch boundary
    (stage1 fail, tier fail, all-generated success incl. the "step never ran"
    vs "step ran and failed" distinction, waiver failure/success, ordinary
    review pass) — 7 direct tests plus 2 CLI-wiring tests plus 5
    classifier-boundary tests (all-generated, one sensitive path mixed in, one
    reviewable path mixed in, empty list, truncated-marker list).
  - *Coverage (breadth):* both delivery paths named in the report — compliance
    refresh (#707-shaped: `.shipwright/compliance/*`, `CHANGELOG-unreleased.d/*`)
    and triage delivery (#708-shaped: `.shipwright/triage.jsonl`) — are covered
    by the *same* `is_generated_path` classifier already exercised by
    `test_pr_review_filter.py`; no new generated-path prefixes were needed.

### Test Completeness Ledger

| Behavior | Status | Evidence |
|---|---|---|
| All-generated, no sensitive path → `classify_generated_only` returns `(True, "no reviewable content - all N paths are generated artifacts")` | tested | `test_review_record_tier.py::test_all_generated_paths_classify_true_with_a_naming_reason` |
| One sensitive path among generated ones → `(False, "")` | tested | `test_review_record_tier.py::test_one_sensitive_path_among_generated_ones_blocks_the_carve_out` |
| One reviewable (non-generated, non-sensitive) path → `(False, "")` | tested | `test_review_record_tier.py::test_one_reviewable_source_path_blocks_the_carve_out` |
| Empty list / truncated-marker list never classify true | tested | `test_review_record_tier.py::test_empty_or_truncated_changed_paths_never_classify_true` |
| CLI emits `all_generated`/`all_generated_reason` outputs | tested | `test_review_record_tier.py::test_cli_emits_all_generated_outputs` |
| `decide_gate`: all-generated + review step never ran → `success` with the naming description (Acceptance 1) | tested | `test_pr_review_gate_verdict.py::test_all_generated_pr_posts_success_with_the_naming_description`, `::test_all_generated_but_review_step_never_reached_also_posts_success` |
| `decide_gate`: sensitive path present (→ `all_generated=False` upstream) still fails when review never ran (Acceptance 2, composed with the classifier test above) | tested | `test_pr_review_gate_verdict.py::test_a_sensitive_path_in_the_mix_means_all_generated_is_false_upstream` |
| `decide_gate`: all-generated=True but review step *did* run and failed/cancelled/timed-out → still `failure` (Acceptance 3) | tested | `test_pr_review_gate_verdict.py::test_model_api_failure_on_an_all_generated_pr_still_fails` |
| `decide_gate`: all-generated=True AND waived (`needs_review=False`) but waiver-consumption fails → still `failure`, never masked by the carve-out (Stage-2 code review finding — an all-generated PR whose sole path is a corroborated `reviews.json` is itself `is_generated_path`, so `all_generated` and `needs_review=False` can coincide) | tested | `test_pr_review_gate_verdict.py::test_all_generated_waived_pr_with_a_failed_waiver_consumption_still_fails` |
| Stage-1/tier failure still fails regardless of `all_generated` | tested | `test_pr_review_gate_verdict.py::test_stage1_failure_fails_regardless_of_all_generated`, `::test_tier_failure_fails_regardless_of_all_generated` |
| Ordinary reviewed/waived PRs keep their exact original descriptions (no regression) | tested | `test_pr_review_gate_verdict.py::test_ordinary_reviewed_pr_still_posts_the_original_descriptions` |
| CLI wrapper (`decide_pr_review_gate.py`) translates step-output strings to `decide_gate` kwargs correctly | tested | `test_decide_pr_review_gate_cli.py` (both cases) |
| Review step's `if:` actually gates on `all_generated != 'true'` (workflow shape) | tested | `test_pr_review_workflow_shape.py::test_generated_only_gate_derived_from_api_changed_paths` |
| Waiver-consumption ordering guarantee, now structural (early-return) rather than text-order | tested | `test_pr_review_gate_verdict.py` early-return coverage above; `test_pr_review_workflow_shape.py::test_failed_waiver_consumption_cannot_post_a_green_gate` (updated shape assertions) |
| `is_safe_to_skip_review`: the three agent-instruction docs are NOT skip-safe (though still `is_generated_path`) | tested | `test_pr_review_generated_skip_review.py::test_the_three_agent_instruction_docs_are_NOT_safe_to_skip` |
| `is_safe_to_skip_review`: an off-canonical path with a generated basename is NOT skip-safe | tested | `test_pr_review_generated_skip_review.py::test_an_off_canonical_path_with_a_generated_basename_is_NOT_safe_to_skip` |
| `is_safe_to_skip_review`: canonical paths, prefixes, and review-evidence stay skip-safe (no regression) | tested | `test_pr_review_generated_skip_review.py` (remaining cases) |
| `decide_gate`: all-generated + waived + failed waiver consumption still fails (not masked) | tested | `test_pr_review_gate_verdict.py::test_all_generated_waived_pr_with_a_failed_waiver_consumption_still_fails` |
| `decide_gate`: all-generated + waived + waiver OK posts the generated reason, pinned | tested | `test_pr_review_gate_verdict.py::test_all_generated_and_waived_pr_posts_the_generated_reason_not_the_tier_reason` |
| Verdict-step `set -e` crash-safety: `gate_out=$(...) \|\| gate_out=""` present | tested | `test_pr_review_generated_only_gate_shape.py::test_gate_decision_script_failure_still_posts_a_status` |
| Review-step `if:` asserts all three conditions, not just the new one | tested | `test_pr_review_generated_only_gate_shape.py::test_generated_only_gate_derived_from_api_changed_paths` |
| End-to-end GitHub Actions execution against a real fork PR | untestable | `reason_code: requires-external-nondeterministic-service` — GitHub Actions `workflow_run` chaining cannot be exercised locally; mitigated by the workflow-shape snapshot tests plus the fully-tested pure decision function it now delegates to |

0 untested-testable behaviors.

## Doubt review findings (Stage 3, addressed before commit)

1. **High.** `classify_generated_only` originally reused `is_generated_path`
   wholesale, which includes `_GENERATED_AGENT_DOCS` — three files this repo's
   own docstring calls "this repo's agent-instruction surface", read back as
   agent context in later sessions. A PR touching only those would skip
   review entirely (converting a pre-existing forced-human-review case into a
   fully automated green, for exactly the files that most need eyes on them).
   **Fixed:** new `pr_review_generated.is_safe_to_skip_review` excludes them;
   `classify_generated_only` now calls it instead of `is_generated_path`.
2. **Medium.** The basename-only matches (`triage.jsonl`,
   `shipwright_events.jsonl`, etc.) matched at any directory, so a brand-new
   file merely named e.g. `plugins/x/triage.jsonl` at an attacker-chosen path
   would classify as skip-safe. **Fixed:** `is_safe_to_skip_review` anchors
   those four basenames to their one canonical repo-root path.
3. **Low.** `decide_gate`'s test parametrized over `"timed_out"` as if it were
   a real GitHub Actions step outcome (it isn't — a timeout surfaces as
   `cancelled`). **Fixed:** replaced with an explicitly-labeled placeholder
   value and a comment explaining why.

## External Code Review (Branch A — codex/openai + glm)

openai: `approve`, no findings. glm: `revise`, four findings:

1. **Medium, accepted-and-fixed.** `gate_out=$(uv run decide_pr_review_gate.py ...)`
   under this step's `set -e` aborts the whole step on a non-zero exit,
   skipping the `gh api .../statuses` call and the "produced no output"
   fallback the step's own comment claimed would catch it — verified
   empirically (`set -e; x=$(false)` does not reach the next line). **Fixed:**
   `|| gate_out=""` keeps the assignment always-succeeding so the existing
   fallback posts an explicit `failure`. Shape-tested
   (`test_gate_decision_script_failure_still_posts_a_status`).
2. **Medium, rejected-with-reason.** Claimed the tier step's bash was never
   changed to emit `all_generated`/`all_generated_reason` to `$GITHUB_OUTPUT`.
   False positive: the tier step's existing invocation line already ends
   `>> "$GITHUB_OUTPUT"` and redirects `review_record_tier.py`'s ENTIRE
   stdout — a generic passthrough, not a fixed set of named captures — so the
   two new `print()` lines `main()` gained flow through unchanged. Verified by
   re-reading `.github/workflows/pr-review-run.yml` lines 203-207 directly.
3. **Low, accepted-and-fixed.** An all-generated + waived + waiver-ok PR posts
   `all_generated_reason` over `tier_reason`, untested and unstated. Pinned
   with `test_all_generated_and_waived_pr_posts_the_generated_reason_not_the_tier_reason`
   and a docstring note.
4. **Low, accepted-and-fixed.** The workflow-shape test for the review step's
   `if:` only asserted the new clause, not the two pre-existing ones.
   Strengthened to assert all three.

## Files changed

- `.github/workflows/pr-review-run.yml` — gate the review step, wire new env,
  replace inline verdict bash with the tested composition call.
- `plugins/shipwright-security/scripts/tools/review_record_tier.py` —
  `classify_generated_only`, new CLI outputs.
- `plugins/shipwright-security/scripts/lib/pr_review_gate_verdict.py` (new) —
  `decide_gate`.
- `plugins/shipwright-security/scripts/tools/decide_pr_review_gate.py` (new) —
  CLI wrapper.
- Tests: `test_review_record_tier.py` (extended), `test_pr_review_gate_verdict.py`
  (new), `test_decide_pr_review_gate_cli.py` (new), `test_pr_review_workflow_shape.py`
  (updated shape assertions for the moved decision logic).
