# Iterate Spec: DeepSeek ZDR external review arm

- **Run ID:** `iterate-2026-08-03-p2-33-deepseek-zdr-review`
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal

Replace the default Gemini outside-review arm with a reviewer that is truthfully
identified as DeepSeek V4 Pro, while keeping the GPT reviewer unchanged. Every
DeepSeek request must stay on an explicitly verified US/EU zero-retention route,
and historical Gemini/OpenAI review evidence must remain readable.

## Acceptance Criteria

- [x] Given either shared external-review client uses OpenRouter, when the two
  review arms are built, then the records and runtime labels are `deepseek` and
  `openai`; the former requests `deepseek/deepseek-v4-pro`, the latter still
  requests `openai/gpt-5.6-terra`, and no DeepSeek result is emitted under a
  `gemini` key.
- [x] Given a DeepSeek OpenRouter request, when its exact outbound body is
  inspected, then `provider.only` and `provider.order` both equal
  `["novita", "together"]`, `provider.allow_fallbacks` is `false`,
  `provider.data_collection` is `"deny"`, and `provider.zdr` is `true`.
- [x] Given the configurable DeepSeek endpoint allowlist is empty, malformed,
  outside US/EU, or lacks an explicit zero-retention verification, when a
  review is attempted, then the DeepSeek arm is unavailable/degraded and no
  request is sent; routing is never widened to Gemini, DeepSeek first-party,
  Singapore, China, an unknown-retention endpoint, or any unlisted provider.
- [x] Given only a direct OpenAI key is configured, when external review runs,
  then GPT may answer through its existing direct route while DeepSeek is
  explicitly unavailable; a Gemini key alone never activates an old fallback.
- [x] Given a historical marker or review payload whose reviewer pair is
  `gemini`/`openai`, when it is read, then its existing verdict and contradiction
  semantics are preserved. Given a new `deepseek`/`openai` pair, the same
  approve/revise/reject, unreadable, unavailable, and contradiction rules apply.
- [x] Given a review record contains an additional reviewer key, when the entry
  is structurally well formed, then it remains readable; when its key and
  `review_type` disagree or any required entry field is malformed, validation
  still fails closed.
- [x] Given shipping configuration and the shared client's built-in defaults,
  when the lockstep test runs, then the DeepSeek and GPT model identifiers and
  timeout agree exactly.
- [x] Given an OpenRouter credential is available, when the synthetic live probe
  runs, then it sends the same fail-closed DeepSeek policy and reports the model
  and selected provider without logging the credential. Without a credential it
  reports an explicit skip rather than pretending the probe passed.
- [x] Given an operator reads the external-review documentation or runtime
  output, when the reviewer pair is named, then it says DeepSeek/OpenAI and
  explains the fail-closed ZDR allowlist; historical Gemini references are kept
  only where they describe backward-compatible reads.

## Spec Impact

- **Classification:** modify
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): `FR-01.03` — outside-review identity,
  fail-closed data route, and historical verdict compatibility;
  `FR-01.11` — forward-compatible review records and current/historical
  reviewer-pair semantics
- **REMOVE** (FR retired → `## Removed Requirements`): none
- **NONE justification:** n/a

## Out of Scope

- Changing the GPT review arm or its selected model.
- Migrating, rewriting, or deleting historical Gemini/OpenAI records.
- Adding an EU endpoint before its location and zero-retention policy are
  deliberately verified and configured.
- Allowing direct DeepSeek, Gemini fallback, model fallback, or provider routing
  outside the configured US/EU ZDR allowlist.
- Changing the overall two-reviewer gate beyond the identity migration and
  backward-compatible verdict handling described above.

## Design Notes

No UI surface is affected. The routing fields and current endpoint facts were
checked against OpenRouter's provider-routing documentation and the DeepSeek V4
Pro provider page on 2026-08-04. The allowlist carries explicit location and
zero-retention verification metadata and must match a code-owned approval
registry, so configuration cannot authorize a provider merely by claiming that
it is safe. A future EU endpoint therefore requires a deliberate code, config,
test, and review change after verification; runtime validation refuses
unsupported regions, unapproved slugs, or unverified entries before constructing
a request.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/config/external_review.json` | `external_review_config.load_review_config`, `llm_review.run_review`, `external_review.py` | JSON configuration |
| `llm_review._review_openrouter`, `external_review.review_with_openrouter` | OpenRouter Chat Completions API | JSON request body |
| `llm_review.run_review`, `external_review.main` | verdict summarizer, marker writer, review-payload parser | JSON reviewer mapping |
| review-record writers, historical committed records | `review_record_schema.validate_record` and downstream readers | JSON review record |

## Confidence Calibration

- **Boundaries touched:** shipping JSON → two request producers; request body →
  OpenRouter; reviewer mapping → verdict/marker consumers; durable review record
  → validators/readers.
- **Empirical probes run:** exact mock-captured request bodies,
  including capture after SDK serialization, hostile routing configs, historical
  record fixtures, new/historical marker round trips, and the credential-gated
  synthetic live probe were recorded before the final canonical F0.
- **Test Completeness Ledger:** complete; every row has passing evidence.

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | exact DeepSeek model, reviewer key, and provider request body in both clients | tested | `test_deepseek_review_routing.py` and `test_external_review_cli.py` passed |
  | 2 | invalid/forbidden/unverified/empty provider configuration fails before network I/O | tested | hostile routing cases in `test_deepseek_review_routing.py` passed |
  | 3 | Gemini credentials and fallback routes cannot activate the DeepSeek arm | tested | credential/fallback cases in `test_external_review_cli.py` and `test_llm_review.py` passed |
  | 4 | current and historical reviewer pairs preserve verdict/contradiction rules | tested | `test_review_verdict_reviewer_migration.py` and `test_review_state_gate.py` passed |
  | 5 | well-formed stranger review keys read; malformed stranger entries fail | tested | `test_review_record_forward_compat.py` passed |
  | 6 | shipping model config and built-in defaults stay in lockstep | tested | lockstep cases in `test_llm_review.py` and `test_external_review_config.py` passed |
  | 7 | synthetic OpenRouter probe uses the production request builder | tested | `test_deepseek_zdr_probe.py` passed and live probe selected `novita` |
  | 8 | runtime labels and external-review documentation name DeepSeek truthfully | tested | installer, UI-plan, and prose/cascade tests passed |

- **Confidence-pattern check:** passed; request, configuration, durable-record,
  historical-reader, runtime-label, and live-provider boundaries are covered.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run shared/scripts/tools/probe_deepseek_zdr.py --project-root . --run-id iterate-2026-08-03-p2-33-deepseek-zdr-review`
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-08-03-p2-33-deepseek-zdr-review/deepseek-zdr-probe.json`
- **Justification (only if surface=none):** n/a
