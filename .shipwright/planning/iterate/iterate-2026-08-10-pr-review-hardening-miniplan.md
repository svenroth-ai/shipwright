# Mini-plan: PR-review stage-two hardening

- **Run ID:** `iterate-2026-08-10-pr-review-hardening`
- **Files:** `.github/workflows/pr-review-run.yml`; `shared/templates/github-actions/claude-review-run.yml.template`; `plugins/shipwright-security/scripts/tools/review_record_tier.py`; direct shared and security regression tests; run-scoped iterate evidence.

1. Port the upstream stage-two history, duplicate-context, cancellation, and checkout-credential controls to both workflow carriers.
2. Read both sides of each changed-file rename and fail closed at GitHub's changed-file API cap; pass the resulting sentinel through the trusted waiver helper.
3. Expand the waiver helper's sensitive-path matcher for suppression and hook-control channels.
4. Add parametrized workflow regression assertions and direct sensitive-path waiver cases.
5. Verify each independent test root and record CI-supplychain acknowledgement; before delivery run the canonical F0 suite, `verify_local.py`, lint, post-push marketplace sync, cache-sync verification, CI, and `deliver_pr.py`.

## Alternative considered

Relying on the final current-head comparison and comments warning stage one not to use the required name was rejected: both controls miss adversarial or transient state that only the timeline/check-runs APIs can observe.
