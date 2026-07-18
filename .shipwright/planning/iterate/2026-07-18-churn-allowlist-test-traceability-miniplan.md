# Mini-Plan: churn-allowlist-test-traceability

## Approach (chosen) — mirror the CI_SECURITY_SUMMARY (CR-1) precedent exactly

`test-traceability.json` is a `.json` compliance snapshot (test_links collector),
re-derived by the same `_update_compliance --phase iterate` producer as the
compliance MDs, but the `.md`-shaped `DERIVED_MDS` missed it — so it was neither
allowlisted (merge ABORTED) nor staged after regenerate (dirty-tree if it fixed).
The identical fix already exists for `ci-security.json`, so this is a 4-site
mirror, not new design:

1. `churn_merge.py` — new `TEST_TRACEABILITY` constant + fold into `CHURN_ALLOWLIST`.
2. `resolve_churn_conflicts.py` — add it to the regenerate staging loop (`out`).
3. `integrate_main.py` — add it to the rollback restore set.
4. `docs/hooks-and-pipeline.md` — a churn-table row (`regenerate`) so the
   both-direction doc-sync test stays green.

## Tests (TDD, done)
- Cloned `test_ci_security_forward_staging.py` → `test_test_traceability_forward_staging.py`:
  allowlist-membership (classify), regenerate-stages, no-phantom-stage, and the
  `category:"integration"` real-git merge-conflict-resolves test.

## Alternative considered (rejected)
Add `test-traceability.json` to `DERIVED_MDS` — rejected: `DERIVED_MDS` is
`.md`-specific (its name/registry test is 1:1 on `.md`), and mixing a `.json`
would break that invariant. Its own constant (like `CI_SECURITY_SUMMARY`) is the
established pattern.

## Risk / safety
- cross_component (churn machinery) → integration test (non-dodgeable, done).
- The 4-site mirror is exact; the CR-1 fix proved allowlist-alone is insufficient
  (must also stage + rollback), which is why all 3 code sites + the doc are touched.
