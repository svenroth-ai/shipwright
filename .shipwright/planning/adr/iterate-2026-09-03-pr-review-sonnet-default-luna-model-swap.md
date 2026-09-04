# Swap PR-review gate default model from GLM 5.3 to GPT-5.6 Luna

## Context

The Tier-3 PR-review CI gate's default model has changed twice before this run:
`anthropic/claude-sonnet-4.6` (original) -> `deepseek/deepseek-v4-pro` (#666, cost) ->
`z-ai/glm-5.3` (#669, after DeepSeek repeatedly hallucinated a confident BLOCK verdict
citing a NameError absent from the diff — a model-quality defect).

GLM 5.3 was then found to silently HANG mid-review on the webui fork's PR #416: the log
shows `[pr_review] reviewing PR #416 with z-ai/glm-5.3 ...`, then 90-170 seconds of total
silence — no exception, no "OpenRouter call failed" print, no timeout message, none of the
script's own error paths fired — then a bare process exit code 1. Reproduced 4 times,
identically, on the same diff, while several sibling PRs using the same GLM 5.3 model
succeeded in the same time window — ruling out a general OpenRouter/provider outage.

Root cause: `pr_review_model_policy.resolve_extra_body()` forces any `deepseek/`- or
`z-ai/`-namespaced model through a hard ZDR (zero-data-retention) compliance constraint
(`shared/scripts/lib/external_review_routing.py`): `provider.order = ["novita",
"together"]`, `allow_fallbacks: false`, `data_collection: "deny"`, `zdr: true`. Only two
resellers, and OpenRouter's normal automatic cross-provider failover is explicitly
disabled by that policy. `novita` serves nearly all GLM traffic (lower measured uptime on
`together`), so this required merge gate ends up hard-dependent on one third-party GPU
reseller, with zero redundancy if it has a bad moment.

## Decision

Default swapped to `openai/gpt-5.6-luna`, NOT back to Sonnet 5 as first proposed. The
initial plan was a like-for-like rollback to `anthropic/claude-sonnet-4.6`/`5` (the model
that predated the ZDR-gated identities and never showed this failure class). The user
asked to check the tradeoff empirically before committing to that, given the price
difference looked "immense": live benchmark/pricing research (2026-09-03) found
SWE-bench Pro 62.7 (Luna) vs 63.2 (Sonnet 5) and Artificial Analysis Intelligence Index 51
vs 53 — no decisive coding-review quality gap for this task — at $0.20/$1.20 per 1M
input/output tokens (Luna) vs $3.00/$15.00 (Sonnet 5), roughly a 15x price difference.

`openai/gpt-5.6-luna` is outside the `deepseek/`/`z-ai/` namespaces the ZDR gate applies
to, so `resolve_extra_body` short-circuits to `{}` — no ZDR pin, ordinary OpenRouter
routing across 3 independent hosts (OpenAI, Azure EU, Amazon Bedrock US), which is *more*
provider-diverse than the 2-reseller ZDR pool that broke GLM, not just cheaper.

DeepSeek and GLM 5.3 both stay wired as `SHIPWRIGHT_PR_REVIEW_MODEL` operator overrides
(unchanged pattern — old defaults are kept, not deleted, matching the DeepSeek precedent
from the prior swap).

## Alternatives Considered (rejected)

- **`anthropic/claude-sonnet-5` rollback** — the first plan. Rejected once the benchmark
  numbers showed near-parity with Luna at ~15x the cost, for a gate whose call volume is
  already low (Tier-3 only: sensitive paths, external contributors, explicit label).
- **Fix GLM's ZDR routing instead (e.g. `allow_fallbacks: true`)** — rejected: the
  `allow_fallbacks: false` constraint is a deliberate zero-data-retention compliance
  requirement shared with the plan/code-review cascade's own GLM identity
  (`external_review_routing.py`); loosening it for this consumer only would mean two
  divergent ZDR policies for the same model family, and would not fix the structural
  2-reseller dependency, only mask it with a non-ZDR-guaranteed fallback.
- **Stay on GLM 5.3, treat the hang as a one-off flake** — rejected: reproduced 4x
  identically, with sibling PRs on the same model succeeding in the same window, which
  rules out "just a flake" and points at something specific to this gate's routing.

## Consequences

The required Tier-3 PR-review CI gate (canonical shipwright and webui — separately
vendored copies, both ported in this run) no longer depends on the narrow ZDR provider
pool for its default path. Per-review cost drops ~15x versus a Sonnet rollback. Existing
DeepSeek/GLM override paths and their tests are unchanged in shape, only re-pointed at
the new default's non-gated behavior.

## Files Touched

- `plugins/shipwright-security/scripts/lib/pr_review_openrouter.py` — new `LUNA_MODEL`
  constant, `DEFAULT_MODEL = LUNA_MODEL`.
- `plugins/shipwright-security/scripts/tools/pr_review.py` — re-export wiring.
- `.github/workflows/pr-review-run.yml` — `SHIPWRIGHT_PR_REVIEW_MODEL:
  openai/gpt-5.6-luna` + explanatory comment.
- `plugins/shipwright-security/tests/test_pr_review_openrouter.py`,
  `test_pr_review_script.py`, `test_pr_review_deepseek_routing.py` — default-model
  assertions updated; the "default delivers ZDR body" test rewritten to "default never
  touches ZDR routing"; a new explicit GLM-override ZDR test added.

Webui port tracked separately per this session's shipwright-then-webui discipline
(mirrors `iterate-2026-09-03-pr-review-block-visibility` / `#674` + `#416`).
