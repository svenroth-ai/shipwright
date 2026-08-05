# Iterate Spec: llm-review-gateway-route

- **Run ID:** iterate-2026-08-05-llm-review-gateway-route
- **Type:** feature
- **Complexity:** medium (manually escalated from the classifier's `small` —
  see Design Notes)
- **Status:** implemented

## Goal
Add a 4th, operator-owned review route — `gateway` — to
`shared/scripts/lib/llm_review.py`, alongside the existing `openrouter` /
`direct` / `none` chain, so an operator whose egress policy requires all
outbound traffic through an OpenAI-compatible gateway (Portkey, Helicone,
LiteLLM proxy, Azure AI Foundry, ...) can route Shipwright's external review
calls (adopt's Layer-3 review + `review_assistant_ui_plan.py`) through it.
Driven by GitHub issue #547 (carlosgil-ai); design agreed with the operator,
who authored the merge-first sequencing (build → review → merge, contributor
validates against his real Portkey/WAF setup afterward on `main`).

## Acceptance Criteria
- [x] `detect_provider()` returns `"gateway"` when
      `SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL` is set, and this is exclusive —
      it wins even when `OPENROUTER_API_KEY`/`OPENAI_API_KEY` are also set.
- [x] The two legs are read from `SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1` /
      `_KEY_MODEL_1` / `_MODEL_2` / `_KEY_MODEL_2` and recorded under the
      generic `model-1`/`model-2` role pair — never aliased onto
      `deepseek`/`openai`.
- [x] Arbitrary `SHIPWRIGHT_REVIEW_GATEWAY_HEADER_<NAME>` env vars are
      forwarded as request headers (e.g. a WAF auth header).
- [x] The gateway route carries no model-identity lock
      (`external_review_routing.resolve_reviewer_model` is never called on
      this path) and no DeepSeek ZDR allowlist check.
- [x] A leg failure (misconfigured slot, network/API error) reports
      `status: "error"` and never falls back to `openrouter`/`direct`, even
      when those keys are present — fail-closed egress.
- [x] The actually-answering model, when the API response reports one, is
      recorded as a separate `answering_model` field, distinct from the
      `model-1`/`model-2` role label.
- [x] `model-1`/`model-2` is registered in
      `review_verdict.GATEWAY_REVIEWERS` / `_SUPPORTED_REVIEWER_SETS`
      alongside `deepseek`/`openai` and the historical `gemini`/`openai`
      pair, so the verdict/contradiction machinery recognizes it without
      further changes.
- [x] Default `openrouter`/`direct`/`none` behavior, the model-identity
      lock, and the DeepSeek ZDR allowlist are unchanged (regression-tested).
- [x] Mocked-HTTP tests cover the above; no real gateway exists to test
      against from this repo, and the test evidence says so plainly rather
      than implying live coverage.
- [x] **(added post-review)** `SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL` must be
      `https://` (or `http://localhost`/`http://127.0.0.1` for local
      testing) — rejected before any network I/O otherwise. Found by
      external plan review (OpenAI arm, high severity).
- [x] **(added post-review)** No secret (per-slot API key, header value, or
      URL userinfo/query-string credential) can appear in a returned error
      `reason`, at either the leg-level catch or `run_review`'s own
      defense-in-depth fallback catch. Found by Stage-2 code review +
      Stage-3 doubt review + external code review (OpenAI arm).
- [x] **(added post-review)** An empty `SHIPWRIGHT_REVIEW_GATEWAY_HEADER_`
      suffix (bare, no `<NAME>`) is ignored rather than producing a blank
      header name. Found by external code review (DeepSeek arm).

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.13 (`/shipwright-adopt`) — its Layer-3 external review
  (`plugins/shipwright-adopt/scripts/lib/review_runner.py`, which calls
  `lib.llm_review.run_review`) can now be routed through an
  operator-configured OpenAI-compatible gateway instead of
  OpenRouter/direct. Folded rather than minted: a pluggable transport for
  external review is plumbing of the review capability FR-01.13 already
  claims, not a new product capability (`shared/fr-authoring.md` §3
  altitude check — "a new route is not by itself a new capability").
  `review_assistant_ui_plan.py`, the other consumer of `llm_review.py`, has
  no FR of its own to fold into (untracked planning-assistant tooling).
- **REMOVE:** none
- **NONE justification:** n/a (classification is not solely `none`)

## Out of Scope
- `shared/scripts/tools/external_review.py` (the CLI used by
  `/shipwright-iterate`'s own `--mode iterate`/`code` external review) is a
  **separate implementation** with its own `detect_provider`/routing
  functions — it does not import from `llm_review.py`. The card scoped this
  change explicitly to `shared/scripts/lib/llm_review.py`; wiring the
  gateway route into `external_review.py` too was not requested and would
  be a second, larger change to Shipwright's own review policy path. Noted
  as a candidate follow-up, not built here.
- No real gateway integration test — mocked HTTP only (see Confidence
  Calibration). carlosgil-ai validates against his real Portkey/WAF setup
  on `main` after merge, per the operator's explicit sequencing decision.
- No changes to the default `openrouter`/`direct` routing logic, the
  model-identity lock, or the DeepSeek ZDR allowlist.

## Design Notes
Not a UI change — no design check applies.

**Complexity escalation.** `classify_complexity.py` auto-scored this
`small` (no keyword match; history fallback capped at `small`). Manually
escalated to `medium` before Step 1 based on positive evidence the
classifier's message-only pass could not see: `CONTRIBUTING.md` names
`shared/` a high-sensitivity path requiring maintainer review, and this
specific change adds new credential-handling / network-egress code to the
file that also implements Shipwright's own review-security policy
(identity lock + ZDR allowlist). Per SKILL.md's Mid-Flight Escalation
allowance, escalating on positive risk evidence is legitimate even when the
keyword/history classifier under-called it.

**Architecture note.** The gateway leg logic (`gateway_headers`/
`review_gateway`/redaction helpers) was extracted into a new sibling module
`shared/scripts/lib/external_review_gateway.py`, and — once the
review-driven hardening (URL validation, redaction) pushed `llm_review.py`
back over the 300-line guideline (the session's bloat-gate Stop hook
correctly blocked on this) — the pre-existing `_review_openrouter`/
`_review_openai` legs were also extracted into
`shared/scripts/lib/external_review_default_legs.py`. `llm_review.py` is
now purely the orchestrator (`detect_provider`/`run_review`) at 221 lines.
This mirrors this package's existing split (`external_review_routing.py` =
locked DeepSeek/OpenAI policy; `external_review_config.py` = config
loading; `external_review_degraded.py` = reply classification) and cleanly
separates "no lock, no ZDR check" gateway code from the locked-down routing
policy it deliberately does not share.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| operator's shell/CI env | `external_review_gateway.review_gateway` | env vars (`SHIPWRIGHT_REVIEW_GATEWAY_*`) |
| gateway's OpenAI-compatible HTTP response | `external_review_gateway.review_gateway` | JSON (via `openai` SDK) |

## Confidence Calibration
- **Boundaries touched:** env-var config surface (`SHIPWRIGHT_REVIEW_GATEWAY_*`
  → `review_gateway`); HTTP response shape from an OpenAI-compatible gateway
  → `review_gateway`'s parsing (`classify_reply`, `answering_model` extraction).
- **Empirical probes run:**
  - Fail-closed precedence: `test_detect_provider_prefers_gateway_over_openrouter_and_direct`
    and `test_run_review_gateway_failure_never_falls_back_to_openrouter_or_direct`
    set gateway config AND openrouter/direct keys together, monkeypatch
    `_review_openrouter`/`_review_openai` to raise `AssertionError` if
    called, and assert they are never invoked when gateway legs fail. PASSED.
  - No identity lock: `test_gateway_leg_accepts_any_model_name_no_identity_lock`
    passes an arbitrary model string through end-to-end and confirms it
    reaches the client's `model=` kwarg unmodified (the default routes would
    raise `ReviewModelPolicyError` here). PASSED.
  - Header round-trip: `test_gateway_arbitrary_headers_pass_through` sets two
    `SHIPWRIGHT_REVIEW_GATEWAY_HEADER_*` vars and asserts both land in the
    client's `default_headers`. PASSED.
  - Answering-model evidence field: both the present and absent cases
    (`test_gateway_leg_records_answering_model_as_separate_evidence_field`,
    `test_gateway_leg_answering_model_absent_when_response_carries_none`)
    are probed — the field is additive, never fabricated. PASSED.
  - Regression: full existing `test_llm_review.py`, `test_review_verdict.py`,
    `test_deepseek_review_routing.py`, `test_review_verdict_reviewer_migration.py`
    suites re-run unmodified and still pass (98/98 across the touched-area
    test files). PASSED.
  - **Ceiling stated plainly:** all of the above mock the `openai.OpenAI`
    client — there is no real gateway (Portkey/WAF or otherwise) to test
    against from this repo. This is mocked-HTTP coverage only, not live
    integration coverage; live validation is carlosgil-ai's post-merge task.
  - **Review cascade (all 6 types recorded in `reviews.json`):**
    `spec-reviewer` PASS (no findings) → `code-reviewer` revise→fixed (4
    findings: Adopt's `_has_any_api_key()` didn't recognize the gateway,
    making the route unreachable from its own named consumer [high]; the
    fail-closed test didn't assert the `deepseek`/`openai` keys were
    *absent* [medium]; no secret redaction on gateway-leg exceptions
    [medium]; only slot 1 was leg-tested [low] — all fixed, see
    `reviews.json`) → `doubt-reviewer` no-block (3 doubts: an unredacted
    defense-in-depth fallback catch [medium, fixed], exact-match-only
    redaction [low, documented as accepted], a docstring citing the wrong
    consumer file [low, fixed]) → external plan review (`--mode iterate`,
    DeepSeek approve / OpenAI revise, not comparable-contradiction since
    within one rank: 5 findings, the actionable ones fixed — https-only
    base URL, header-suffix/Authorization-precedence documentation) →
    external code review (`--mode code`, DeepSeek approve / OpenAI revise:
    URL-embedded credentials [userinfo/query] could leak into an error
    `reason` via the unsanitized validation message — fixed with
    `_sanitize_url_for_display`/`_url_secret_parts`; empty header-suffix env
    var — fixed with a guard). Every reviewer's actionable finding was
    fixed, not merely recorded; the two accepted-as-documented items
    (exact-match redaction, no SDK-transport-level test) are explicit
    trade-offs stated in this file, not silent gaps.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `detect_provider` returns `gateway` when base URL set | tested | `test_detect_provider_returns_gateway_when_base_url_set` PASSED |
  | 2 | gateway takes exclusive precedence over openrouter/direct | tested | `test_detect_provider_prefers_gateway_over_openrouter_and_direct` PASSED |
  | 3 | default chain unchanged when gateway unset | tested | `test_detect_provider_falls_back_normally_without_gateway_configured` PASSED |
  | 4 | missing `MODEL_<slot>` → error (not skip) | tested | `test_gateway_leg_missing_model_env_is_error_not_skip` PASSED |
  | 5 | missing `KEY_MODEL_<slot>` → error | tested | `test_gateway_leg_missing_key_env_is_error` PASSED |
  | 6 | arbitrary model name passed through, no identity lock | tested | `test_gateway_leg_accepts_any_model_name_no_identity_lock` PASSED |
  | 7 | `answering_model` recorded when present in response | tested | `test_gateway_leg_records_answering_model_as_separate_evidence_field` PASSED |
  | 8 | `answering_model` absent when response omits it | tested | `test_gateway_leg_answering_model_absent_when_response_carries_none` PASSED |
  | 9 | `base_url`/`api_key` passed to the client | tested | `test_gateway_leg_passes_base_url_and_key_to_client` PASSED |
  | 10 | arbitrary `HEADER_<NAME>` vars forwarded | tested | `test_gateway_arbitrary_headers_pass_through` PASSED |
  | 11 | API/network exception → `error` status, reason captured | tested | `test_gateway_leg_api_error_is_error_status` PASSED |
  | 12 | `run_review` success uses `model-1`/`model-2` role pair | tested | `test_run_review_gateway_success_uses_model_1_model_2_role_pair` PASSED |
  | 13 | `run_review` gateway failure never falls back | tested | `test_run_review_gateway_failure_never_falls_back_to_openrouter_or_direct` PASSED |
  | 14 | `model-1`/`model-2` registered in `review_verdict` | tested | `test_gateway_reviewer_pair_is_registered_in_review_verdict` PASSED |
  | 15 | existing `deepseek`/`openai` and `gemini`/`openai` pairs undisturbed | tested | `test_deepseek_openai_and_gemini_openai_pairs_still_supported` PASSED |
  | 16 | Adopt's `_has_any_api_key()` recognizes a gateway-only config | tested | `test_gateway_only_env_does_not_skip_before_llm_review_runs` PASSED |
  | 17 | `_has_any_api_key()` still skips with nothing configured | tested | `test_no_provider_configured_at_all_still_skips` PASSED |
  | 18 | `run_review`'s defense-in-depth fallback catch also redacts | tested | `test_run_review_gateway_fallback_catch_also_redacts_secrets` PASSED |
  | 19 | leg-level error redacts key + header secrets | tested | `test_gateway_leg_error_message_redacts_key_and_header_secrets` PASSED |
  | 20 | slot 2 reads its own distinct model/key env vars | tested | `test_gateway_leg_slot_2_reads_its_own_model_and_key_env_vars` PASSED |
  | 21 | both slots configured together, no cross-contamination | tested | `test_both_slots_configured_together_use_their_own_distinct_values` PASSED |
  | 22 | insecure `http://` base URL rejected, no network call attempted | tested | `test_insecure_http_base_url_is_rejected_before_any_network_call` PASSED |
  | 23 | `http://localhost` / `127.0.0.1` allowed for local testing | tested | `test_http_localhost_is_allowed_for_local_testing` PASSED |
  | 24 | `https://` base URL accepted | tested | `test_https_base_url_is_accepted` PASSED |
  | 25 | custom header overrides SDK-generated `Authorization` | tested | `test_custom_authorization_header_overrides_the_sdk_generated_one` PASSED |
  | 26 | gateway leg never reads `OPENROUTER_API_KEY`/`OPENAI_API_KEY` | tested | `test_gateway_never_reads_openrouter_or_direct_env_vars` PASSED |
  | 27 | insecure-URL error message never echoes embedded credentials | tested | `test_insecure_url_error_never_echoes_embedded_credentials` PASSED |
  | 28 | empty `HEADER_` suffix ignored, not sent as a blank header | tested | `test_empty_header_suffix_env_var_is_ignored_not_sent_as_a_blank_header` PASSED |
  | 29 | live behavior against a real gateway (Portkey/WAF) | untestable | requires-external-nondeterministic-service — no real gateway reachable from this repo; carlosgil-ai validates post-merge on `main` |
  | 30 | SDK-level request construction (URL joining, header serialization) against a real `openai.OpenAI` transport, not a fake client | untestable | covered-by-existing-test — `test_custom_authorization_header_overrides_the_sdk_generated_one` already exercises the real `openai.OpenAI` construction path for header precedence, the one SDK-internal behavior this diff actually depends on (external plan review, OpenAI arm, flagged the fakes generally; a full mock-transport harness for every call shape was judged disproportionate to what a config-plumbing change needs) |

- **Confidence-pattern check:** Asymptote (depth) — the fail-closed
  no-fallback property was the one place a first pass could plausibly have
  been wrong (e.g. accidentally reusing the openrouter/direct branch logic),
  so it got a dedicated adversarial probe (`_boom` raises `AssertionError`
  if the old routes are touched) rather than just asserting the final
  `provider` field. Coverage (breadth) — every row above is `tested` or
  `untestable` with a valid reason_code; 0 untested-testable rows.
  **Integration composition:** this change does not touch
  `cross_component` framework machinery (merge/churn/hooks/campaign), so no
  additional integration-coverage behavior is owed.

## Verification (medium+)
- **Surface:** none (library/CLI code, no startable dev server or CLI
  entry point of its own — `llm_review.run_review` is a Python function
  imported by other tools, not a runnable surface)
- **Runner command:** n/a
- **Evidence path:** n/a
- **Justification (only if surface=none):** `shared/scripts/lib/llm_review.py`
  and its new sibling module are library code with no independent CLI/web
  surface; their only consumers (`review_assistant_ui_plan.py`,
  `plugins/shipwright-adopt/scripts/lib/review_runner.py`) are themselves
  invoked deep inside the `/shipwright-adopt` and plan-review flows, not
  directly startable. Coverage is via the unit/mocked-HTTP test suite above
  (F0 fresh verification gate), consistent with how the existing
  `openrouter`/`direct` routes in this same file are verified.
