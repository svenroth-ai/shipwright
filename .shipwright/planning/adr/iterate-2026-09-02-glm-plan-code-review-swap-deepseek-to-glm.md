# Replace DeepSeek with GLM 5.3 as the plan/code-review cascade's second reviewer

## Context

The internal plan/code-review cascade (`shared/scripts/tools/external_review.py`
and its supporting `shared/scripts/lib/external_review_*.py`/`review_*.py`
modules) pairs GPT (direct or OpenRouter) with a second, cheaper reviewer
identity for a genuine second opinion. That second identity was DeepSeek
(`deepseek/deepseek-v4-pro`, via OpenRouter). Live testing this session (direct
OpenRouter API probes, not speculation) established that DeepSeek reliably
degrades on large diffs by exhausting its entire output-token budget on
invisible reasoning tokens (`finish_reason: length`, near-empty visible
content) — a content/reasoning-budget failure, not a provider-availability
one (both of DeepSeek's two configured ZDR providers, `novita` and `together`,
were separately confirmed live and reachable). DeepSeek additionally exhibits a
second, distinct client-side parsing failure (`TypeError: 'NoneType' object is
not subscriptable`) unrelated to the reasoning-budget issue, unaffected by a
larger `max_tokens` or a `reasoning.effort` cap. Gemini Pro (used elsewhere in
this project's history, not this cascade) was independently found degraded the
same way. The user's underlying goal was explicitly cost reduction: GPT-5.6-terra
(direct) is expensive, Opus is used via subscription for internal review roles,
and a reliable, not-too-expensive complement to both was needed specifically
for plan and code review.

## Decision

Replace DeepSeek with GLM 5.3 (`z-ai/glm-5.3`, via OpenRouter,
`novita`/`together` US ZDR-verified providers — the same two already vetted
for DeepSeek) as the cascade's second reviewer identity, with
`reasoning.effort: "low"` capped in the OpenRouter request body. GLM 5.3
shares DeepSeek's reasoning-budget degradation pattern on large diffs, but
that failure mode is reliably fixed by the reasoning-effort cap (verified live
this session: 28.7s, a full substantive review, ~$0.02/call, against the real
merged diff of PR #670). The reviewer-role key literal `"deepseek"` is renamed
to `"glm"` everywhere it names that role across the cascade (config, routing
identity-lock bindings, marker/verdict/payload schemas, CLI flags, checks) —
not just the model string — so no residual "deepseek"-as-a-live-identity
literal remains in the cascade's own code path.

DeepSeek's ZDR routing primitives (`APPROVED_DEEPSEEK_ENDPOINTS`,
`DeepSeekRoutingPolicyError`, `deepseek_openrouter_extra_body`, the
`deepseek_routing` config block) are deliberately **kept, not deleted** — this
was discovered mid-implementation, not planned up front. They are directly
imported by `plugins/shipwright-security/scripts/lib/pr_review_model_policy.py`,
which is the **Tier-3 PR-review CI gate** (a structurally separate consumer,
already swapped to GLM 5.3 as its own default in an earlier, already-merged
iterate) and offers DeepSeek as an operator-overridable choice via
`SHIPWRIGHT_PR_REVIEW_MODEL=deepseek/...` per ADR-167. Deleting the shared
primitives would have broken that unrelated, already-shipped feature.
`plugins/shipwright-security`'s own files are untouched by this diff except a
single accuracy-only docstring correction in `probe_glm_zdr.py` (see Files,
below) — a factual reference to a file this diff deletes, corrected to past
tense.

`review_marker.MARKER_SCHEMA` bumps 3→4 (new glm/openai roster). Both older
rosters remain readable: schema 3 (deepseek/openai, itself the historical
roster from before this swap) and schema 2/None/1 (gemini/openai, from before
DeepSeek). `review_companion.write_markers`/`repair_markers` now branch three
ways (gemini→2, deepseek→3, glm/current→4) and explicitly reject any other
verdict shape (e.g. the operator-owned gateway route's `model-1`/`model-2`
pair) rather than silently mis-stamping it as schema 4 — this hardening was
added during the internal Stage-3 doubt review (see Review, below).

## Alternatives Considered (rejected)

- **Mistral `devstral-2512`** (EU-native, cheapest) — no comparable
  general-reasoning benchmark to weigh against GLM 5.3's AA Intelligence Index
  (59.5); SWE-bench Verified alone is not a substitute for review-quality
  signal.
- **Moonshot `kimi-k2-thinking`** — cheap, available via an already-approved
  provider, but AA Intelligence Index only ~19-33, well below GLM 5.3 despite
  a comparable/better SWE-bench score.
- **`x-ai/grok-4.6`** — US first-party hosting, but priced the same as
  GPT-5.6-terra — no cost win, the entire point of this change.
- **`qwen/qwen3-max`** — ruled out outright: no US/EU OpenRouter hosting route
  exists at all (Alibaba-only), failing the hosting-region requirement before
  cost or quality were even compared.

## Consequences

The cascade's cost/reliability profile improves for plan and code review
without changing any user-visible external-review capability (review still
runs, still produces the same JSON envelope shape and marker/verdict
contract). An operator with a stale `SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_DEEPSEEK`
env var set for this cascade now has it silently ignored (the model key no
longer exists in `_VALID_MODEL_KEYS`) rather than validated — an accepted,
low-severity consequence of removing a config knob that no longer applies,
surfaced and accepted during external code review (see Review, below).

## Files Touched

Config: `shared/config/external_review.json` (`deepseek_routing`→ kept
inert + `glm_routing` promoted to the active binding; `models.openrouter_glm`
replaces `models.openrouter_deepseek`).

Routing/identity-lock: `shared/scripts/lib/external_review_routing.py`,
`external_review_config.py`.

Cascade consumers: `shared/scripts/lib/external_review_default_legs.py`,
`external_review_degraded.py`, `external_review_gateway.py`, `llm_review.py`,
`backfill_llm.py` (TT6 backfill adjudicator — a separate feature reusing the
same shared config/routing, updated so it keeps working once the DeepSeek
model key left `_VALID_MODEL_KEYS`), `shared/scripts/tools/external_review.py`,
`backfill_test_links.py`, `review_assistant_ui_plan.py`.

Schema/verdict/marker: `review_marker.py` (schema 3→4), `review_payloads.py`,
`review_verdict.py`, `review_companion.py` (schema-selection hardening, see
Review).

CLI/checks: `shared/scripts/checks/check-external-review-keys.py`,
`mark-review-state.py`, `shared/scripts/validate_env.py`.

Docs/skill references: `docs/guide.md`, `docs/hooks-and-pipeline.md`, and the
`plugins/shipwright-plan|build|iterate` skill-reference files that name the
cascade's reviewer identities. One accuracy-only docstring correction in
`plugins/shipwright-security/scripts/tools/probe_glm_zdr.py` (past-tense fix
for a comment referencing the now-deleted `probe_deepseek_zdr.py`).

Deleted (obsolete, DeepSeek-only): `shared/scripts/tools/probe_deepseek_zdr.py`,
`shared/tests/test_deepseek_zdr_probe.py`,
`shared/tests/test_deepseek_review_routing.py`.

Tests: `shared/tests/test_glm_review_routing.py` (repurposed 1:1 from the
deleted DeepSeek routing test, extended with request-body round-trip and
cross-identity-contamination coverage), `test_review_verdict_reviewer_migration.py`,
`test_review_marker_companion_verdicts.py`, plus ~20 other test files updated
for the roster rename, and `shared/scripts/tools/tests/test_backfill_engine_units.py`.

## Self-Review

All 8 checklist items pass or n/a (Performance Basics: n/a — no DB/loop
changes). Full detail: `.shipwright/planning/iterate/iterate-2026-09-02-glm-plan-code-review-swap-self-review.json`,
recorded in the run's review record (`--review-type self`).

## Internal Review Cascade

- **spec-reviewer (Stage 1):** PASS — all 7 points of the stated intent
  verified against the diff; no scope creep, no missed rename, DeepSeek
  primitives confirmed correctly kept-but-unbound.
- **code-reviewer (Stage 2):** PASS (clean) — one low-severity readability nit
  (a type-distinctness test assertion for `GlmRoutingPolicyError`/
  `DeepSeekRoutingPolicyError` was not carried into the security plugin's own
  test file). **Disposition: rejected-with-reason** — `plugins/shipwright-security`
  is out of scope for this iterate; the invariant is unchanged and still
  implicitly exercised by both classes being raised independently elsewhere.
- **doubt-reviewer (Stage 3, triggered by cross-plugin coupling + a versioned
  schema migration):** raised 4 doubts. Two addressed with a code fix before
  commit:
  - *Medium — schema-branch exhaustiveness not self-defending*: `write_markers`/
    `repair_markers` derived `marker_schema` purely from the verdict roster
    with no re-validation of their own, so a gateway-route (`model-1`/`model-2`)
    or any other unrecognized set could silently fall through to schema 4 —
    the exact bug class already found (see External-Code-Review-Findings)
    and fixed for the historical DeepSeek roster, just pushed one layer
    further. **Fixed**: `write_markers` now explicitly raises
    `ReviewRecordError` for any verdict set outside `{REVIEWERS,
    *HISTORICAL_REVIEWER_PAIRS}`, with a new regression test
    (`test_write_markers_rejects_an_unrecognized_verdict_roster`).
  - *Low — stale doc reference*: `probe_glm_zdr.py`'s docstring referenced the
    now-deleted `probe_deepseek_zdr.py` in present tense. **Fixed** (docstring
    only, past tense correction).
  - *Low — reduced DeepSeek-specific mutation-matrix coverage*: the deleted
    `test_deepseek_review_routing.py`'s 8-case mutation matrix exercised
    `deepseek_openrouter_extra_body` directly; the security plugin's own test
    covers only one case for that still-live primitive. **Disposition:
    accepted, not fixed** — the shared `_provider_openrouter_extra_body`
    validation logic is still fully exercised via the GLM mutation matrix
    (both functions call it), and expanding `plugins/shipwright-security`'s
    test suite is out of scope for this iterate.
  - *Low — backward-compat tests prove shape-equivalence, not disk-fidelity*:
    no test reads a literal pre-existing on-disk marker/record fixture written
    before this PR. **Disposition: accepted** — the marker's field set is
    unchanged (only the schema-number/roster mapping changed), so risk is low;
    a frozen-fixture regression test is a reasonable future addition, not a
    blocker here.

## External-Code-Review-Findings

External review ran twice: once against an initially incomplete diff file
(missing staged file deletions — a local diff-generation mistake, not a code
defect; both external reviewers' "deletion not present" finding was a false
positive caused by that, confirmed false via direct `git status`/`git diff
HEAD` inspection), and once, authoritatively, after regenerating the diff
correctly and fixing the one real bug found below.

- **HIGH (openai + glm, independently) — `review_companion.py` schema-write
  bug**: `write_markers` only special-cased the historical gemini/openai
  roster; every other roster (including the historical deepseek/openai one)
  fell through to `MARKER_SCHEMA` (now 4), so repairing a pre-swap
  deepseek/openai record would write a schema-4 marker carrying a deepseek
  roster, which `evaluate_review_state` then blocks. **accepted-and-fixed**:
  three-way branch (gemini→2, deepseek→3, current→4), plus the doubt-review
  hardening above; re-ran full targeted + suite tests, green.
- **LOW (glm) — legacy env-var override silently ignored**:
  `SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_DEEPSEEK` no longer resolves to anything
  since `openrouter_deepseek` left `_VALID_MODEL_KEYS`. **accepted-with-reason**
  — this is the intended effect of removing a config knob for an identity the
  cascade no longer offers; not a security or correctness issue.
- **LOW (glm) — output-key rename (`providers.deepseek`→`providers.glm`) in
  `check-external-review-keys.py`**: no programmatic consumer of that key
  exists anywhere in this repo (grepped); it is read by an agent following
  skill prose at runtime, not parsed by a fixed downstream script.
  **rejected-with-reason** — no actual consumer breaks; the rename is the
  intended behavior change.
- **LOW (glm) — gateway-roster edge case in `write_markers`**: raised
  independently by the external GLM reviewer and by the internal doubt-reviewer
  (see above). **accepted-and-fixed** together with the doubt-review item.
- Re-run after the fix: both `openai` and `glm` legs return
  `SHIPWRIGHT_VERDICT: approve` with no remaining findings.

## Rationale

Cost reduction while keeping review quality: GLM 5.3's general-reasoning score
(AA Intelligence Index 59.5) was not clearly beaten by any US/EU-hosted,
ZDR-verified, price-comparable alternative surveyed. The reasoning-effort cap
is an empirically-verified fix for the one failure mode GLM 5.3 shares with
DeepSeek; DeepSeek's second, distinct client-side failure mode has no known
fix and is not present in GLM 5.3.
