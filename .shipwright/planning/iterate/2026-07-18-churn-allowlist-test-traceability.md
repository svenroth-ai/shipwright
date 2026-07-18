# Iterate Spec: churn-allowlist-test-traceability

- **Run ID:** iterate-2026-07-18-churn-allowlist-test-traceability
- **Type:** change
- **Complexity:** medium (cross_component → integration coverage enforced)
- **Status:** draft

## Goal
Add `.shipwright/compliance/test-traceability.json` to the churn merge-conflict
allowlist so `ensure_current` / `integrate_main` / `resolve_churn_conflicts` stop
ABORTING on it during `origin/main` reconciliation — the gap that forced a manual
`--theirs` in iterate #391. Mirror the existing `CI_SECURITY_SUMMARY` (CR-1)
precedent **exactly**: allowlist + stage-on-regenerate + rollback + doc row.

## Acceptance Criteria
- [ ] **AC1 (allowlist):** new `TEST_TRACEABILITY =
  ".shipwright/compliance/test-traceability.json"` constant in `churn_merge.py`
  (its own constant like `CI_SECURITY_SUMMARY`, NOT folded into `DERIVED_MDS` —
  it's a `.json`, and the `.md`-specific registry test must stay 1:1) folded into
  `CHURN_ALLOWLIST`. `complete_merge` resolves a conflicted test-traceability.json
  via the `--theirs` placeholder path instead of aborting.
- [ ] **AC2 (regenerate + STAGE):** `regenerate_tracked_snapshots` includes
  `TEST_TRACEABILITY` in the staged `out` set (`COMPLIANCE_MDS | {CI_SECURITY_SUMMARY,
  TEST_TRACEABILITY}`), so the freshly re-derived file is `git add`ed and reaches
  the follow-up commit — NOT left modified-but-unstaged (the CR-1 dirty-tree bug).
  `integrate_main`'s rollback set also includes it.
- [ ] **AC3 (integration — cross_component):** a real-git merge with a two-sided
  conflict on `test-traceability.json` resolves (not aborts) through
  `integrate_main.integrate` → `status == "ok"`, `"regenerated-followup" in steps`,
  the follow-up commit carries fresh content, and `git status --porcelain` is
  clean. (Cloned from `test_ci_security_forward_staging.py`'s integration test +
  a cascade case in `test_parallel_merge_cascade_integration.py`.)
- [ ] **AC4 (doc-sync):** a row for `test-traceability.json` (strategy keyword
  `regenerate`) added to the churn-reconciliation table in
  `docs/hooks-and-pipeline.md`, so `test_churn_merge_doc_sync.py`'s both-direction
  `documented == CHURN_ALLOWLIST` guard stays green.

## Spec Impact
- **Classification:** none
- **NONE justification:** infrastructure/tooling — extends the merge-conflict
  churn-reconciliation machinery to cover an existing generated artifact. No
  user-visible FR. Finalize `change_type` = `infra`.

## Out of Scope
- No change to what the compliance producer generates (test-traceability.json is
  already re-derived by `_update_compliance --phase iterate`).
- No change to the resolve-strategy for other artifacts.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `test_links.generate_file` | `resolve_churn_conflicts` / `integrate_main` staging | JSON snapshot |
| `churn_merge.CHURN_ALLOWLIST` | `classify` / `complete_merge` + doc-sync test | allowlist set |

## Confidence Calibration
- **Boundaries touched:** the churn-reconciliation allowlist + the
  regenerate-and-stage set + the integrate rollback set.
- **Empirical probes run:** (before F0)
  - Reproduce: a conflicted test-traceability.json currently ABORTS
    `complete_merge` (preflight, outside allowlist); after the fix it resolves.
  - Stage: after regenerate, `git status --porcelain` has NO unstaged
    test-traceability.json (it reached the follow-up commit).
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | test-traceability.json in CHURN_ALLOWLIST → not `blocking` | tested | unit (classify) |
  | 2 | regenerate stages test-traceability.json when rewritten | tested | unit (out/staged) |
  | 3 | regenerate does not phantom-stage when unchanged | tested | unit |
  | 4 | real merge conflict resolves through integrate, clean tree | tested | integration (real-git), `category:integration` |
  | 5 | doc table ↔ CHURN_ALLOWLIST both-direction | tested | test_churn_merge_doc_sync |

- **Confidence-pattern check:** depth — the CR-1 precedent proves "allowlist alone
  is insufficient; must also stage" (the probe confirms the dirty-tree failure
  mode). breadth — every row tested; integration composition covered (AC3).

## Verification (medium+)
- **Surface:** none
- **Runner command:** n/a (framework merge-tooling; no startable app surface)
- **Evidence path:** `shipwright_test_results.json` (pytest incl. the real-git
  integration test)
- **Justification (surface=none):** plugin-library merge-reconciliation tooling;
  verified end-to-end by the real-git merge-conflict integration test.
