# Iterate: PR-review stage-two hardening

- **Run ID:** `iterate-2026-08-10-pr-review-hardening`
- **Type / Complexity:** change / medium
- **Triage:** `trg-36ceef43` (P3.07, IT-9)
- **Affected FR:** FR-01.17 — Independent re-check on the code host
- **Spec impact:** NONE — FR-01.17 already requires automatic independent host review that cannot be self-exempted; this closes implementation gaps in that existing promise.

## Problem and outcome

The credentialed second stage of the PR-review gate must only publish a verdict for the exact branch history it reviewed, remain the sole producer of its required context, and never let a review waiver cover the files that control scanner or hook silence.

## Acceptance criteria

1. A verdict fails closed if the PR head changed or any `head_ref_force_pushed` event occurred after stage 1 started, including an A-to-B-to-A restore.
2. Before posting, stage 2 refuses a head SHA that already has a check run using its exact required-context name.
3. A cancelled, superseded stage-2 job never posts a late verdict; the live run still posts failures for ordinary prior-step failures.
4. Both stage-2 checkouts set `persist-credentials: false`, while retaining only the explicit permissions required for API actions.
5. `skip-pr-review` cannot waive changes to scanner suppressions (all supported Trivy ignore forms and Semgrep), accepted-risk configuration, agent settings, bloat baseline, or installed hook paths/installers — including a renamed protected path or an API-truncated changed-path list.

## Boundaries and non-goals

- **In scope:** `.github/workflows/pr-review-run.yml`, the shipped stage-two template, waiver tier policy, and their direct regression tests.
- **Out of scope:** stage-one policy, branch-protection configuration, the reviewer's model behavior, and other IT-9 workflow cards.
- **No stored-format boundary changed.**

## Decision

Use the existing trusted `workflow_run` event's `run_started_at` as the lower bound for the PR timeline query, then refuse on either a changed head or a force-push event. Use the checks API read scope only to detect a second required-context producer. This is narrower and safer than changing stage one or branch-protection policy.

## Test plan

- Parse both local and shipped stage-two workflows to prove each of the four workflow controls.
- Exercise the waiver decision helper for every newly-sensitive suppression and hook path, including a truncated-path sentinel.
- Run the focused shared and security test roots separately, as required by ADR-044.

## Verification (medium+)

- **Surface:** CLI/configuration; no browser or server surface is changed.
- **Commands:** `pytest shared/tests/test_pr_review_fail_closed.py shared/tests/test_pr_review_fork_trust.py -q` and `pytest plugins/shipwright-security/tests/test_review_record_tier.py plugins/shipwright-security/tests/test_pr_review_workflow_shape.py -q`, each in its own test root.
- **Evidence:** focused output is recorded in the run's F5 test ledger; F0 will run the repository's canonical suite and F0.5 records a `surface=none` justification.

## Internal Plan Review (plan-reviewer)

- **Ran:** yes
- **Severity:** medium
- **Summary:** Scope matches the five P3.07 protections; the review required explicit verification, renamed-path/API-cap coverage, a complete file manifest, and the plugin cache-sync delivery step.
- **Findings:** verification — fixed in this spec; plan completeness — fixed in this spec and mini-plan; delivery procedure — added to mini-plan; stale cross-card wording — excluded because `trg-36ceef43` is authoritative.
- **Known limitations:** external plan review could not run because the platform declined repository-content transmission; this is recorded separately, not treated as a pass.
- **Status:** 3 fixed, 1 disclosed
