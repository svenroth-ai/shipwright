# Iterate: Codex CLI as a second GPT review leg

- **Run ID**: iterate-2026-09-03-codex-cli-review-leg
- **Type**: feature
- **Complexity**: medium (operator override — cross-cutting shared-lib
  change touching both external-review consumers, a new subprocess
  integration, and identity-locked config; classifier returned `small` at
  confidence 0.5, below the threshold to trust unreviewed)
- **Spec Impact**: MODIFY (extends the existing external-review system;
  no new spec section, no behavior change for operators who don't opt in)
- **Status**: implemented

## Problem

Shipwright's external-review system answers the "openai" reviewer identity
(GPT) via OpenRouter or direct OpenAI — both metered per token. The operator
has a flat-cost ChatGPT/Codex subscription and wants the option to route
that leg through the Codex CLI instead, cutting the per-review API cost of
that leg to zero, without changing behavior for operators who don't have
Codex.

## Acceptance Criteria

- [x] **AC1**: A new `review_codex()` leg in
  `shared/scripts/lib/external_review_default_legs.py` answers the "openai"
  reviewer identity via `codex exec`, reusing the existing free-form-text +
  `SHIPWRIGHT_VERDICT` sentinel contract (`review_verdict.py`) — no new
  output schema, since the shipped reviewer prompts already ask for prose,
  not JSON.
- [x] **AC2**: An availability check (`is_codex_available()`) detects whether
  `codex` is installed and authenticated for this operator, without ever
  raising.
- [x] **AC3**: Route selection is config-driven: `external_review.gpt_leg.provider`
  in `shared/config/external_review.json` (shipped default `"api"` —
  unchanged existing behavior) and per-project override via
  `shipwright_iterate_config.json` (deep-merged, existing mechanism).
- [x] **AC4**: When configured for `"codex"` but codex is unavailable for this
  operator, the leg gracefully falls back to the existing OpenRouter/direct
  route (if a key is configured), or skips with a stated reason — never a
  hard failure.
- [x] **AC5**: The Codex model identity is locked the same way GLM/GPT are
  today — `resolve_reviewer_model` rejects a configured value that doesn't
  match the code-owned binding; `models.codex` in the shipped config.
- [x] **AC6**: Both consumers (`shared/scripts/tools/external_review.py` CLI,
  `shared/scripts/lib/llm_review.py` library) dispatch through the same
  route-resolution logic, and the GLM leg's dispatch stays independent of
  the openai-leg's route choice (a mixed pass — GLM via OpenRouter, GPT via
  Codex — is a valid, expected state).
- [x] **AC7**: Existing behavior is provably unchanged for operators who don't
  configure `"codex"` — every existing external-review test still passes
  unmodified.
- [x] **AC8**: Documented in `docs/hooks-and-pipeline.md` (config data-flow
  table) and `docs/guide.md` where the external-review system is described.

## Non-Goals

- No Codex-CLI route for the GLM reviewer identity (GLM has no Codex
  equivalent — it stays OpenRouter-only, unchanged).
- No env-var override for the route choice (config-only, matching the
  task's "config-driven... not silently overridable" requirement).
- No change to the Tier-3 PR-review gate (`pr_review_model_policy.py`) —
  out of scope, a separate consumer with its own model policy.

## Design

See `.shipwright/planning/iterate/iterate-2026-09-03-codex-cli-review-leg-MINIPLAN.md`.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** no (not spawned)
- **Severity:** n/a
- **Summary:** This mandatory medium+ sub-step (always before Branch A/B/C, mirroring
  `/shipwright-plan` Step 5-int) was not executed at its normal point in the workflow —
  disclosed here rather than fabricated retroactively. The external plan review (GLM
  approve / GPT revise via `external_review.py --mode iterate`, recorded under `plan`)
  did run at that point and independently covered plan-quality concerns (compatibility
  probe gap, security/sandbox exposure, subprocess lifecycle, degradation-generalization
  risk — see the `plan` row's findings). Build then proceeded through spec-reviewer →
  code-reviewer → doubt-reviewer (10 findings, 9 fixed) and two full external
  code-review cascade passes (GLM + GPT, both round-trip verified against the actual
  diff) before this disclosure was written, so the change was not left unreviewed —
  only this one specific independent pass, over the mini-plan rather than the diff, is
  missing.
- **Findings:** n/a — pass did not run
- **Known limitations:** none disclosed by this pass (it never ran)
- **Status:** not_run

## Confidence Calibration

- **Boundaries touched:** subprocess invocation of an external CLI
  (`codex exec`); shared config (`shared/config/external_review.json`)
  consumed by 4+ plugins; per-project config override
  (`shipwright_iterate_config.json`).
- **Empirical probes run:**
  - Real `codex exec` invocation with the exact argv `review_codex()` builds
    (`-m gpt-5.6-terra --skip-git-repo-check --sandbox read-only --ephemeral
    --ignore-user-config --ignore-rules --cd <scratch dir> -o <file>`),
    prompt via stdin, against the installed/authenticated Codex CLI
    (v0.147.0). Result: exit 0; `-o` file contained exactly
    `SHIPWRIGHT_VERDICT: approve` — confirms the whole flag set is accepted
    by the real binary, the model name resolves, and the final-message file
    is written in the shape `classify_reply` expects. This is the probe
    Stage-2 code-reviewer's re-review flagged as missing (a wrong flag would
    otherwise hard-fail every real pass with no way to catch it pre-merge).
  - Prior probes (recorded in the mini-plan): `--sandbox read-only
    --ephemeral --ignore-user-config --ignore-rules` verified to keep codex
    from seeing the real repo/operator config while `codex login status`
    still authenticates via `$CODEX_HOME`.
- **Test Completeness Ledger:**
  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | AC1: review_codex answers via codex exec, reuses SHIPWRIGHT_VERDICT contract | tested | test_review_codex_sends_the_rendered_prompt_with_no_residual_placeholder, test_cli_codex_route_actually_sends_the_spec_and_plan_not_the_raw_template |
  | AC2: is_codex_available never raises (missing binary / not authenticated / timeout / OSError / symlink-loop RuntimeError) | tested | test_unavailable_when_binary_not_on_path, test_unavailable_when_not_authenticated, test_unavailable_on_login_status_timeout, test_unavailable_on_oserror_never_raises, test_resolve_codex_binary_never_raises_on_a_symlink_loop |
  | AC3: gpt_leg.provider config-driven, deep-merged per-project | tested | test_gpt_leg_provider_reads_the_configured_value, test_load_review_config_round_trip_per_project_overrides, test_cli_codex_route_actually_sends_the_spec_and_plan_not_the_raw_template (writes real file, drives real loader) |
  | AC4: graceful fallback to API route or skip when codex unavailable | tested | test_resolve_openai_route_falls_back_to_api_when_codex_unavailable, test_resolve_openai_route_falls_back_to_skip_when_neither_is_usable, test_run_review_records_fallback_reason_on_a_successful_fallback_leg |
  | AC5: codex model identity locked, rejects mismatched config | tested | test_codex_binding_accepts_the_locked_model, test_codex_binding_rejects_a_different_configured_model, test_review_codex_rejects_a_model_identity_mismatch |
  | AC6: both consumers share route resolution; GLM dispatch independent of GPT route | tested | test_gpt_leg_routes_through_codex_when_project_configures_it (CLI), test_run_review_routes_openai_leg_through_codex_when_configured (library) — both assert glm stays "skipped"/independent |
  | AC7: existing (non-codex) behavior provably unchanged | tested | full pre-existing external_review/llm_review suite (210 tests) passes unmodified; test_resolve_openai_route_default_config_matches_legacy_api_chain pins the legacy chain bit-for-bit; test_*_degraded_generalization.py pins is_degraded/is_partially_degraded old-vs-new equivalence per previously-allowlisted combination |
  | AC8: documented in guide.md + hooks-and-pipeline.md | tested | covered-by-existing-test — spec-reviewer round-4 PASS explicitly verified both doc citations (guide.md:1514, hooks-and-pipeline.md:2950) |
  | shutil.which cwd-hijack guard (BatBadBut) | tested | test_resolve_codex_binary_cwd_hijack_guard |
  | codex_settings / gpt_leg_provider defensive parsing of malformed config | tested | test_codex_settings_clamps_a_negative_max_retries, test_codex_settings_defaults_when_unconfigured, test_codex_settings_falls_back_to_defaults_on_a_non_mapping_codex_config, test_gpt_leg_provider_falls_back_to_api_on_an_unhashable_value |
  | Real `codex exec` invocation accepts the exact argv this leg builds | untestable | reason_code: requires-interactive-tty — the authenticated real binary is this operator's local Codex CLI session; CI has no Codex subscription to authenticate with. Mitigated by the empirical probe above (real binary, real argv, real output) run manually in this session and recorded here, not by an automated test. |
  - `counts`: testable=10, tested=9, untestable=1, untested_testable=0.
- **Confidence-pattern check:** The "are you confident?" self-check produced yes-then-bug twice in this run — both caught, not shipped: (1) the doubt-reviewer pass found the `shutil.which` cwd-hijack gap after I had already called binary resolution "safe" post-empirical-probe; (2) the first external code-review pass found `user_prompt.replace(None)` (verified FALSE on inspection — `run_review` already defaults `user_prompt` before that line) alongside three genuinely real bugs (`gpt_leg_provider`/`codex_settings` TypeError on malformed config, `is_codex_available` not catching `RuntimeError` from a symlink loop) that a "tests pass" confidence check had missed. Per the asymptote rule, one more probe was run after each: a second, diff-complete external review pass (untracked test files included via `git add -N`) confirmed no new high/medium findings beyond documented accepted risks, closing the loop.
