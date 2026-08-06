# Mini-Plan: llm-review-gateway-route

- **Run ID:** iterate-2026-08-05-llm-review-gateway-route

## Files to create/modify
- `shared/scripts/lib/external_review_gateway.py` — new. Gateway leg logic:
  `gateway_configured`, `gateway_headers`, `review_gateway`,
  `_redact_secrets`, `redact_all_configured_secrets`, URL-scheme validation.
- `shared/scripts/lib/external_review_default_legs.py` — new (added after
  the review cascade pushed `llm_review.py` back over 300 lines).
  `review_openrouter`/`review_openai`, extracted unchanged from
  `llm_review.py`.
- `shared/scripts/lib/llm_review.py` — edit. `detect_provider()` gains
  gateway precedence; `run_review()` gains the gateway branch (exclusive
  if/elif); now purely the orchestrator, importing both leg modules.
- `shared/scripts/lib/review_verdict.py` — edit. `GATEWAY_REVIEWERS =
  ("model-1", "model-2")` registered into `_SUPPORTED_REVIEWER_SETS`.
- `plugins/shipwright-adopt/scripts/lib/review_runner.py` — edit.
  `_has_any_api_key()` widened to recognize a configured gateway (found
  during Stage 2 code review — the route was otherwise unreachable from its
  own named consumer).
- `shared/tests/test_llm_review_gateway.py`,
  `test_llm_review_gateway_detect.py`, `test_llm_review_gateway_routing.py`,
  `plugins/shipwright-adopt/tests/test_review_runner_gateway_reachable.py` —
  new, mocked-HTTP.

## Work breakdown
1. Register `GATEWAY_REVIEWERS` in `review_verdict.py` (additive, no
   existing-pair disturbance). Test: pair comparable, existing pairs intact.
2. Write failing tests for `detect_provider`/`_review_gateway`/`run_review`
   gateway behavior (TDD red).
3. Implement `external_review_gateway.py` + wire `llm_review.py`'s
   `detect_provider`/`run_review`. Tests green.
4. Self-review (8-point checklist) + iterate spec Confidence Calibration.
5. Review cascade: spec-reviewer (HARD-GATE) → code-reviewer → doubt-reviewer.
   Fix findings from each stage before proceeding (reachability gap, secret
   redaction, test strengthening — see reviews.json for the full record).
6. Finalize: F0–F11, commit, PR, arm auto-merge per the operator's explicit
   merge-first sequencing decision (issue #547, carlosgil-ai validates
   post-merge against his real Portkey/WAF setup).

## Test strategy
Mocked-HTTP unit tests only (`monkeypatch.setattr(openai, "OpenAI", ...)`)
— no real gateway reachable from this repo, stated explicitly rather than
implying live coverage. No E2E: this is library code with no startable
surface (see spec's `## Verification` section).

## Alternative approach considered (medium — required)
**Alternative:** wire the gateway route into
`shared/scripts/tools/external_review.py` (the CLI `/shipwright-iterate`
itself uses for `--mode iterate`/`code`) instead of, or in addition to,
`shared/scripts/lib/llm_review.py`.

**Why rejected:** `external_review.py` is a separate implementation with its
own `detect_provider`/routing functions — it does not import from
`llm_review.py` at all. Wiring the gateway into it would be a second, larger
change touching Shipwright's own review-policy path (the mechanism that
gates `/shipwright-iterate`'s and `/shipwright-plan`'s own review cascades),
which was explicitly not requested by the card and would need its own
design discussion given how security-sensitive that specific path is. The
card scoped this change to `llm_review.py`'s two actual consumers (Adopt's
Layer-3 review, `review_assistant_ui_plan.py`). Noted as a candidate
follow-up in the spec's Out of Scope section, not built here.
