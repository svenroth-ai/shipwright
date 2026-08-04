# Mini-Plan — `iterate-2026-08-03-p2-33-deepseek-zdr-review`

Intent CHANGE, complexity medium (locked). Spec Impact MODIFY for FR-01.03 and
FR-01.11. This AUTO card carries the operator's plan approval while its scope
remains unchanged.

## Chosen approach

Make the reviewer identity and the fail-closed DeepSeek policy shared facts,
then route both existing OpenRouter clients and a small synthetic probe through
that policy. Keep historical compatibility in readers only: new writers emit
`deepseek`/`openai`, while verdict readers accept that pair and the historical
`gemini`/`openai` pair. Identity-lock every active arm to the
operator-selected model so configuration or environment overrides cannot move
DeepSeek through the GPT route or label a different model as `deepseek`.

| Step | Files | Change and test expectation |
|---|---|---|
| 1 | `shared/tests/test_deepseek_review_routing.py`, existing external-review/config tests | RED: pin the exact request body from both clients after SDK serialization, prove the GPT body has no DeepSeek routing policy, model/default/timeout lockstep, rejected allowlists, no Gemini fallback, and credential-gated probe behavior |
| 2 | `shared/config/external_review.json`, `shared/scripts/lib/external_review_config.py`, new small routing helper | Replace Gemini defaults with DeepSeek V4 Pro; require configurable endpoint metadata to match a code-owned approved-provider registry and build one canonical complete provider policy that refuses empty, changed-order, added, missing, malformed, unverified, or non-US/EU routes |
| 3 | `shared/scripts/tools/external_review.py`, `shared/scripts/lib/llm_review.py`, `shared/scripts/lib/external_review_degraded.py` | Replace runtime Gemini arms and labels, remove direct-Gemini selection, attach the DeepSeek policy on every DeepSeek OpenRouter request, preserve the direct GPT arm, and surface routing-policy failures as unavailable/degraded |
| 4 | `shared/scripts/lib/review_verdict.py`, `shared/scripts/checks/mark-review-state.py`, verdict/marker tests | Treat `deepseek`/`openai` as the current pair while preserving read behavior for historical `gemini`/`openai` markers; pin contradictions, unreadable verdicts, one-arm degradation, and fail-closed mixed/triple generation mappings |
| 5 | `shared/scripts/lib/review_record_schema.py`, review-record tests | Accept and validate well-formed additional reviewer keys without adding them to the required/write vocabulary; reject malformed stranger entries |
| 6 | `shared/scripts/tools/probe_deepseek_zdr.py` and tests | Add a minimal synthetic live probe that reuses production config/policy, uses only fixed non-sensitive content, writes a redacted run-scoped evidence schema, skips explicitly without credentials, and never persists headers, raw request/response bodies, or credential-bearing exceptions |
| 7 | external-review runtime labels/docs, `docs/hooks-and-pipeline.md`, `docs/guide.md`, FR spec | Document DeepSeek/OpenAI, exact ZDR routing, fail-closed behavior, configurability, and historical Gemini read compatibility |
| 8 | affected pytest roots, canonical F0, ruff, `verify_local.py` | Run one pytest root per process. Defer final canonical F0 until P1.12 is delivered on `origin/main`, integrated with the prescribed helper, and its plugin cache is synchronized |

## Data/configuration changes

The shipping review config replaces Gemini model keys with DeepSeek keys and
adds a DeepSeek endpoint allowlist. Each entry carries provider slug, processing
region, and explicit zero-retention verification, while code owns the approved
slug/region registry and canonical order. Current config must resolve exactly to
`novita`, `together`; a future EU addition deliberately changes registry,
config, tests, and review together. This is configuration, not a durable schema
migration; historical outputs are not rewritten.

Code also owns the exact reviewer/model bindings:
`deepseek/deepseek-v4-pro`, `openai/gpt-5.6-terra`, and direct
`gpt-5.6-terra`. The shared resolver still observes configuration and
environment values, but every producer rejects a differing resolved value
before client construction.

## Test strategy

- Unit-test the canonical builder and capture the serialized HTTP body at an SDK
  mock-transport boundary for each OpenAI-compatible client.
- Assert the GPT OpenRouter body contains none of the DeepSeek provider policy.
- Inject hostile config and environment model overrides in both directions and
  prove they fail before client construction.
- Parameterize hostile allowlists: missing, empty, duplicate/malformed entries,
  false or absent zero-retention verification, CN/SG/unknown regions, and
  unlisted providers; assert zero client calls.
- Exercise no-key, OpenRouter-only, direct-OpenAI-only, and Gemini-key-only
  selection without changing the GPT behavior.
- Round-trip current and historical marker/verdict payloads and review records.
- Treat a mixed `gemini`/`deepseek`/`openai` marker as ambiguous and require
  resolution; a structurally valid stranger review-record row remains readable
  but does not become a vote.
- Run the synthetic probe live only when `OPENROUTER_API_KEY` exists; otherwise
  record the explicit credential skip as `requires-prod-credential`.
- Run every affected pytest root in its own process, then the canonical runner,
  pinned ruff, and local merge guards.

## External plan review disposition

The OpenRouter plan review returned `approve`/`revise` with no hard
contradiction. Accepted: DeepSeek-only request scoping; a shared complete policy
builder; SDK-transport body capture; code-owned authorization plus configurable
declaration; explicit three-arm fail-closed behavior; model and timeout
lockstep; redacted fixed-content probe evidence; and targeted/root verification
before the dependency lands.

Rejected with reason:

- Removing outbound `provider.zdr`: OpenRouter's current official routing
  documentation explicitly supports it, and the operator requires it.
- Making arbitrary configuration metadata sufficient authorization: config must
  match the code-owned verified registry instead.
- Running final canonical F0 before P1.12: the operator explicitly requires the
  final canonical run only after P1.12's host-resource lease is on main and the
  plugin cache is synchronized. Targeted tests and affected roots run earlier;
  the iterate cannot complete or deliver without the later canonical pass.

## Internal spec-review disposition

The first Stage-1 spec review returned `REVISE` with one high security
finding: model overrides could route the DeepSeek model through the OpenAI arm
without the ZDR policy, or emit another model under the `deepseek` identity.
Accepted and fixed by adding a central code-owned reviewer/model binding used by
the CLI, shared library, backfill adjudicator, and live probe. Hostile
config/env overrides now fail before client construction and are covered by
dedicated tests. The Stage-1 pass is re-run on that correction before later
cascade stages.

Stage 2 initially returned `REVISE` for two low documentation mismatches that
still described model values as freely overridable. Both API/module contracts
now describe identity-locked declarations and the re-review returned
`APPROVE`.

Stage 3 confirmed four counterexamples: non-success peers were not always
partial; probe evidence could overstate a pre-request failure; setup still
treated Gemini-only credentials as active; and one compliance label presented
Gemini as current. All four were accepted and fixed with regression tests.
The probe now distinguishes attempted from confirmed-sent calls, partial
reviews name every non-success arm, setup ignores retired Gemini keys, and the
collector labels Gemini historical. The repeated doubt pass returned
`APPROVE`.

## External code-review disposition

The first code review returned DeepSeek `APPROVE` and OpenAI `REVISE` without
a hard contradiction. OpenAI correctly identified the reviewer-roster change
as a breaking payload change that could not continue under marker schema 2.
Accepted and fixed: current markers now emit schema 3, while the reader keeps
accepting historical schema-2 Gemini markers and older unversioned markers.
The external-review JSON envelope now explicitly emits review schema 2 on all
JSON exit paths; its historical Gemini/OpenAI schema 1 was implicit. Contract
tests pin both new versions and the historical marker read path. A repeated
external code review ran on this corrected diff: both arms completed, DeepSeek
returned `APPROVE`, and OpenAI returned `REVISE`, again without a hard
contradiction.

Accepted from the repeated pass: add the missing aggregate-level unit test for
the direct-OpenAI path. It proves that a direct GPT success keeps the DeepSeek
arm explicitly skipped/unavailable and marks the result partial.

Rejected with evidence:

- OpenAI's two high syntax-corruption findings: the cited source line is the
  valid tuple `("{PLAN}", "{DIFF}", "{SPEC}")`, the cited test call is the
  valid short template `"{PLAN} {SPEC}"`, Ruff parsed both files, and the
  focused pytest process collected and passed 70 tests. The model conflated
  the separately appended iterate specification with the preceding diff.
- Extending top-level warnings when zero arms succeed: the established
  aggregate contract deliberately reserves `partial`/warnings for a usable
  but incomplete result; a zero-success result is `success: false`, and its
  per-arm `reviews` carry the diagnostic reasons. Existing tests pin this
  distinction, so changing it would be unrelated contract churn.

## Alternative considered

Keep a `gemini` compatibility alias in new output and merely swap the model
behind it. Rejected because it makes the durable record lie about reviewer
identity, prevents consumers from distinguishing historical Gemini evidence
from new DeepSeek evidence, and directly violates the operator's no-alias rule.
Compatibility therefore belongs in readers, never in new writes.
