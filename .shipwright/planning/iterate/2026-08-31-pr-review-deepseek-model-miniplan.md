# Mini-Plan: pr-review-deepseek-model

- **Run ID:** iterate-2026-08-31-pr-review-deepseek-model

## Files to create/modify
1. `plugins/shipwright-security/scripts/lib/pr_review_openrouter.py` — edit:
   change `DEFAULT_MODEL`, add a `resolve_extra_body(model, config)` helper,
   thread an `extra_body: dict | None = None` param through `call_openrouter`
   / `_post_openrouter` into the JSON payload.
2. `plugins/shipwright-security/scripts/tools/pr_review.py` — edit: load
   `shared/config/external_review.json` via `external_review_config.load_review_config()`,
   call `resolve_extra_body(model, config)`, pass the result to
   `call_openrouter(...)`, catch `DeepSeekRoutingPolicyError` alongside the
   existing boundary-error handling (fail closed, `EXIT_ERROR`).
3. `.github/workflows/pr-review-run.yml` — edit: `SHIPWRIGHT_PR_REVIEW_MODEL`
   → `deepseek/deepseek-v4-pro`.
4. `plugins/shipwright-security/tests/test_pr_review_openrouter.py` — edit:
   update the hardcoded default-model assertion; add tests for
   `resolve_extra_body` (deepseek → ZDR body, other model → `{}`, broken
   config → raises) and that `_post_openrouter`'s payload includes `provider`
   when `extra_body` is passed.
5. `plugins/shipwright-security/tests/test_pr_review_script.py` — edit:
   update the hardcoded default-model assertion; add a test that `main()`
   returns `EXIT_ERROR` (no OpenRouter call attempted) when the model is
   DeepSeek and `deepseek_routing` config is malformed.
6. `.shipwright/planning/iterate/iterate-2026-08-31-pr-review-deepseek-model/ci_supplychain_ack.json`
   — new, via `record_ci_supplychain_ack.py` (`touches_ci_supplychain` fired
   on `.github/workflows/pr-review-run.yml`).

## Work breakdown

**Revised after external plan review** (openai + deepseek, both `revise`,
converged on the same core issue — see `## External LLM Review` in the
iterate spec): the original draft called `load_review_config()`
unconditionally for every model, so a broken/absent `external_review.json`
would break PR review even for a non-DeepSeek override — directly violating
AC3 ("no DeepSeek-specific handling for another model"). Fixed by
short-circuiting on model identity BEFORE any config load.

1. `pr_review_openrouter.py`:
   - Add one named constant, `DEEPSEEK_MODEL = "deepseek/deepseek-v4-pro"`,
     and set `DEFAULT_MODEL = DEEPSEEK_MODEL` — one literal, not a duplicated
     string across `DEFAULT_MODEL`/the comparison/tests/the workflow file.
   - Add `resolve_extra_body(model: str) -> dict`: if `model != DEEPSEEK_MODEL`,
     return `{}` **immediately, without importing or loading any config** —
     this is the short-circuit the review demanded. Only on the DeepSeek
     branch does it import `load_review_config` and
     `deepseek_openrouter_extra_body`/`DeepSeekRoutingPolicyError` from
     `shared/scripts/lib/external_review_config.py` /
     `external_review_routing.py` (both from the SAME module import, so the
     exception type caught by the caller is guaranteed to be the one raised)
     and return `deepseek_openrouter_extra_body(load_review_config())`.
     Any exception from either call (missing/malformed JSON, bad routing
     config) propagates — the caller (below) is the single place that maps
     it to fail-closed, so there is one boundary, not two.
   - Extend `_post_openrouter`/`call_openrouter` with a **keyword-only**
     trailing parameter `*, extra_body: dict | None = None` (never inserted
     before existing positional params, so no existing call site/test
     breaks) that gets merged into `payload` (`payload.update(extra_body)`)
     before serializing, only when truthy.
   Test: `resolve_extra_body` unit tests — DeepSeek branch returns the ZDR
   body (mock `load_review_config`), non-DeepSeek branch returns `{}` with
   config loading NEVER attempted (assert the mock is not called), and a
   broken `deepseek_routing` config propagates `DeepSeekRoutingPolicyError`
   uncaught at this layer. Payload-merge test confirms the no-`extra_body`
   call keeps today's exact payload shape (regression guard for AC3).
2. `pr_review.py`: after resolving `model`, wrap ONLY
   `resolve_extra_body(model)` in `try/except (DeepSeekRoutingPolicyError,
   OSError, json.JSONDecodeError)` (the loader's documented failure modes,
   caught alongside the routing error so a malformed `external_review.json`
   fails exactly the same way as a malformed `deepseek_routing` block) —
   prints a redacted error and returns `EXIT_ERROR` **before** `fetch_pr_diff`
   or `call_openrouter` run, mirroring the existing boundary-error pattern in
   `main()`. Pass the resulting `extra_body` into
   `call_openrouter(..., extra_body=extra_body)`.
   Test: `main()` fail-closed test with a monkeypatched broken
   `deepseek_routing` config AND one with unreadable/malformed
   `external_review.json` — both must return `EXIT_ERROR` with zero
   `call_openrouter` invocations (assert the mock was never called, not just
   the exit code).
3. Update the two test files' hardcoded model-string assertions to
   `pr_review_openrouter.DEEPSEEK_MODEL` (import the constant, don't
   re-hardcode the literal a third time).
4. `pr-review-run.yml`: one-line env var change to the same literal.
   Test: strengthen `test_pr_review_workflow_shape.py`'s existing
   presence-only assertion into a value assertion (`SHIPWRIGHT_PR_REVIEW_MODEL:
   deepseek/deepseek-v4-pro` present in stage 2's env block) — the reviewers
   flagged that the presence-only check would pass even on a stale/wrong
   value.
5. Record the CI-supply-chain acknowledgement, `--consistent-with ADR-167`
   (Tier-3 PR review via OpenRouter custom-script — this change stays inside
   that same architecture) with a statement naming the model swap + the
   reused ZDR routing constraint.

## Test strategy
- Unit tests only (mocked OpenRouter transport, no live network/API key) —
  matches the existing style in `test_pr_review_openrouter.py`.
- No E2E needed — no UI, no dev server (`Verification: surface = none` in the
  iterate spec).
- Full run of `plugins/shipwright-security/tests/` at F0.

## Alternative approach considered
**Inline the ZDR-routing body construction directly in `pr_review_openrouter.py`**
instead of importing `deepseek_openrouter_extra_body` from
`external_review_routing.py`. Rejected: the ordered ZDR provider allowlist
(`novita`, `together`) is a security-reviewed, fail-closed decision this repo
already made once for this exact model — duplicating the validation logic
would let the two call sites (review cascade vs. CI gate) drift apart
silently (e.g. one gets a fix for a new region check, the other doesn't).
Importing the single shared function keeps both DeepSeek call sites bound to
one code-owned policy.
