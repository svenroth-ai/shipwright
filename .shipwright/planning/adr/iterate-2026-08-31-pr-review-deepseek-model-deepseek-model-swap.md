# Tier-3 PR-review gate: DeepSeek model swap with reused ZDR routing

## Context

The Tier-3 CI PR-review gate (`pr_review.py`) called
`anthropic/claude-sonnet-4.6` via OpenRouter. `deepseek/deepseek-v4-pro` is
far cheaper and faster per call, and the review cascade's own DeepSeek arm
already carries a fail-closed ZDR (zero-data-retention) provider-routing
policy this gate could reuse rather than reimplement.

## Decision

Swap `DEFAULT_MODEL` to `deepseek/deepseek-v4-pro` (workflow env var updated
to match). Add `pr_review_model_policy.py`, which resolves an OpenRouter
`extra_body` for the resolved model: for a `deepseek/`-namespace model it
loads `shared/config/external_review.json` and returns the same
`deepseek_openrouter_extra_body()` constraint the review cascade already
enforces (novita/together only, `allow_fallbacks: false`,
`data_collection: deny`, `zdr: true`); for any other model it returns `{}`
WITHOUT ever loading that config, so a non-DeepSeek operator override (a
Sonnet rollback, say) can never be broken by that config's health. `main()`
resolves this before any network call and fails closed (`EXIT_ERROR`) on a
broken/malformed routing config.

## Consequences

The gate is materially cheaper per PR review. It now depends on
`shared/config/external_review.json`'s health for DeepSeek calls specifically
(added to `review_record_tier.py`'s `SENSITIVE_PATH_RE` so a config-only
drift is itself reviewed). ZDR's `allow_fallbacks: false` plus the
documented lack of a live `together` endpoint for this model leaves exactly
one live provider (novita) serving this REQUIRED merge gate; a rollback PR
editing the hardcoded model id is reviewed by the DEFAULT BRANCH's own
(possibly still-broken) copy of the workflow (GitHub `workflow_run`
semantics), so recovery from a provider outage is a maintainer's
`gh pr merge --admin` on the rollback PR — documented as a comment next to
`SHIPWRIGHT_PR_REVIEW_MODEL` in `pr-review-run.yml` rather than engineered
around, per this iterate's decision not to build canary/rollback machinery
beyond a live production-payload test.

## Rationale

Reuse over reimplementation: the ZDR policy is code-owned and already
validated against an exact provider allowlist; duplicating it would be a
second place for that allowlist to drift. The non-DeepSeek short-circuit
(checked BEFORE any config import/load) is what an internal and an external
plan reviewer both independently flagged in the first draft — the fix moved
the DeepSeek-identity check ahead of anything network- or config-bound.

## Rejected alternatives

GLM 5.3 / GLM 5.3 Flash were considered but not live-tested against this
gate's exact payload shape in this iterate; DeepSeek was already proven via
the review cascade. Adding a second live ZDR provider (closing the
single-provider gap) was rejected as out of scope — it edits
`deepseek_routing`'s own values, which this iterate explicitly does not
touch, and the user's own decision was that a live test is sufficient
without additional rollback engineering.

**Full detail:** [2026-08-31-pr-review-deepseek-model.md](../iterate/2026-08-31-pr-review-deepseek-model.md)
— Goal, Acceptance Criteria, Internal + External Plan Review, Architecture
Review, Confidence Calibration + Test Completeness Ledger, Code Review
(Stage 1+2, 6 findings all fixed), Doubt Review (Stage 3, 5 doubts all
addressed), Verification.
