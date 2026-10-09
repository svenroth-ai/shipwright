# Iterate: finish the review-gateway route (issue #547 follow-up)

- **Run ID:** iterate-2026-10-09-issue-547-followup
- **Type:** change (bug fixes + one additive field) — **Complexity:** small (classifier `small`, Stage-2 scout found no medium trigger; no cross-split, no cross-component machinery)
- **Spec Impact:** modify (FR-01.13 — adopt's Layer-3 review; shared review plumbing)
- **Status:** implemented

## Why

#572 added the `gateway` route to `llm_review.py` (Adopt only). Validating it against a real Portkey gateway
(@carlosgil-ai, 2026-08-16 and after) showed the transport is right and that the rest of the pipeline never
learned about it. Triumph1701 asked that the record state the effective provider/model and whether a gateway/WAF
route was used.

## Acceptance criteria (assertion-shaped)

1. With only `SHIPWRIGHT_REVIEW_GATEWAY_*` set, `external_review.py --mode iterate|plan|code|architecture` returns
   `provider: "gateway"`, reviews `model-1`/`model-2`, exit 0 when either answers; with `OPENROUTER_API_KEY` /
   `OPENAI_API_KEY` also set, neither is called (fail-closed, no fallback).
2. `get_external_review_status()` / `is_external_review_enabled()` return `available` with only the gateway set, and
   `check-external-review-keys.py` reports `providers.gateway: true`.
3. A completed gateway pass can be recorded: `schema_for_roster({"model-1","model-2"}) == 6`, `evaluate_review_state`
   accepts it and rejects a `glm`/`openai` roster under schema 6; `record_review_pass.py` accepts the envelope.
4. Every `external_review.py` envelope (key route, gateway route, empty-diff, early failure) carries `reviewed` (`reviews_succeeded > 0`; `false` on the last two); `llm_review.run_review` (Adopt) is out of scope; when a run exits 0 having attempted nothing, a stderr notice says the
   review did NOT run (early failures exit 1 with an `error`, which is already loud). `success` semantics are unchanged.
5. The gateway leg sends `max_completion_tokens` first and retries once with `max_tokens` only when the gateway says
   the parameter is UNSUPPORTED (structured `unsupported_parameter`, or "unsupported" wording) - a value error or an
   echoed-kwargs body is never retried; a failed retry keeps both errors. The configured `max_retries` reaches the client.
6. Every gateway leg result (success AND error, incl. missing model/key, insecure URL, missing `openai`) carries
   `gateway_evidence {host (scheme+host only, no path), header_names (names only), token_param}`; no key or header
   value appears in any result.
7. `plugins/shipwright-adopt` declares `openai` and `jsonschema`; a failed review leg's `reason` is written to
   `review.md`; `validate_adoption` warns when no review leg succeeded (still `ok: true` for a documented skip).
8. The gateway variables are scaffolded into a NEW `.env.local` (never reported as `missing_keys`, never appended to
   an existing file; a filled gateway base URL also drops the two key vars from `missing_keys`) and documented in `docs/guide.md` (Option E + env table).
9. `--stamp-adopted` with an abbreviated sha says why (full 40-character sha required) instead of the generic
   "no usable commit".

## Decisions

- `success` is NOT flipped to false for "nothing attempted": provider `none` is the documented missing-keys state
  that callers branch on (existing tests pin it). The honest signal is the additive `reviewed` flag + stderr notice.
- Abbreviated shas stay refused (documented security reasoning in `resolve_adopted_base`); only the message changed.
- Gateway roster joins `CURRENT_REVIEWER_ROSTERS` and gets marker schema 6 rather than being aliased onto glm/openai.
- Out of scope (declined): model-capability metadata, retry/fallback policy knobs, a pluggable "connector" layer.

## Affected boundaries

Producer `external_review.py` stdout → consumer `record_review_pass.py` / `review_payloads` / `review_marker`
(round-trip covered by `test_gateway_roster_has_its_own_marker_schema`); `.env.local` scaffold → `parse_env_file`.
