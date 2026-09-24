# Section Context — Model version bump (iterate-2026-09-24-model-version-bump)

No iterate spec file exists for this run (small complexity, CHANGE, Spec
Impact = NONE — a provider-neutral requirement's literal model identifier is
an operational parameter, not a described behavior). This file stands in as
the review-cascade's spec reference.

## What changed

A pure rename of retired/bumped upstream model identifiers, wherever they
appear in live config, routing code, docs prose, CI, and the tests that
assert those literals. No logic, schema shape, or control flow changed —
only string literal values.

1. **Internal-review cost tracking** (`model_pricing.py`,
   `context_cost_readiness.py`): `claude-opus-5` -> `claude-opus-5-5`, with
   the pricing table's rates updated to the real Opus 5.5 rates ($4.00 input
   / $20.00 output per MTok, operator-supplied).
2. **External review "opus" identity** (`external_review.json`,
   `external_review_routing.py`, `llm_review.py`, `docs/guide.md`):
   `claude-opus-5` -> `claude-opus-5-5` / `anthropic/claude-opus-5` ->
   `anthropic/claude-opus-5-5`.
3. **Codex-side model retirement**: `gpt-5.6-terra` (execution/finalization +
   "openai" reviewer identity) is retired; `gpt-5.6-sol` (the Codex review
   model) is bumped. Both collapse to the single new name `gpt-6-sol` (bare)
   / `openai/gpt-6-sol` (OpenRouter-prefixed) across
   `external_review.json`, `external_review_routing.py`, `llm_review.py`,
   `codex_review_transport.py`, and doc/prompt prose.
4. **CI PR-review model**: `openai/gpt-5.6-luna` -> `openai/gpt-6-luna`, in
   both the CI workflow's env var and the module's own local-fallback
   default (`pr_review_openrouter.py`), so local and CI runs agree.

`AGENTS.md` is explicitly excluded — it is being removed in a parallel
effort, and touching it here would just add prose that is about to be
deleted anyway.

## Why

Upstream model catalog updates (Anthropic: Opus 5 -> 5.5; OpenAI-side: Terra
retired, Sol bumped to v6, Luna bumped to v6). Shipwright pins exact model
identifiers in several places for review-identity-lock reasons (never a
floating alias) — those pins need to track the new names.

## Risk flags

`touches_ci_supplychain` fired (`.github/workflows/pr-review-run.yml`
touched) — acknowledgement recorded at
`.shipwright/planning/iterate/iterate-2026-09-24-model-version-bump/ci_supplychain_ack.json`,
consistent with `iterate-2026-09-03-pr-review-sonnet-default` (the prior
model-swap of the same shape). No other risk flags fired (no
`cross_component`, `io_boundary`, or `touches_build` — confirmed via
`risk_detectors.py` against the full changed-file list).
