# Architecture Brief: opus-review-leg-codex-driver

## The problem

`external_review.py`'s external-review roster is hard-coded to `{glm, openai}`
regardless of which harness produced the diff being reviewed. When a
Codex-CLI-driven session runs external review, the "openai" leg
(`gpt-5.6-terra`) reviews code that Codex itself — same vendor, frequently the
same model family — just wrote. This happens on every Codex-driven run today
and is silent: the output looks identical to the genuinely independent case
where Claude drives and GPT reviews.

## What already exists here

- `external_review.py`: a CLI with four review modes, each dispatching GLM
  plus one other identity in parallel.
- `external_review.gpt_leg.provider`: a config knob that already lets the
  "openai" identity's own transport route through the Codex CLI, OpenRouter,
  or direct API — but the identity answering that leg stays "openai" either
  way.
- `shipwright_model_config.json` / the Claude-only agent-tier resolver
  (opus/sonnet/haiku/inherit): a separate axis, scoped to Claude Code's own
  Agent-tool subagents, not to external review.

## What would newly, permanently exist

A third reviewer identity ("opus": Claude, reached via a local CLI transport
with an OpenRouter fallback) and a required CLI flag selecting which pair of
identities answers a review, kept correct going forward by: the roster the
flag selects, the model-identity lock each leg validates against, and every
prose call site across three plugins that must keep passing the flag.

## Options on the table

- **A:** Add a third, cross-vendor reviewer identity and a flag that swaps it
  in for "openai" specifically when Codex drove the diff.
- **B:** Do nothing — accept that a Codex-driven run's external review is a
  same-vendor check, not an independent one.
- **C:** Make the existing GPT leg's Codex-CLI transport route (`gpt_leg.provider:
  codex`) refuse to fire when the diff itself came from Codex, falling back to
  direct/OpenRouter OpenAI instead — same vendor family reviews, different
  specific transport.
- **D:** Build a generic, pluggable multi-identity/multi-driver framework
  (config-driven roster resolution, extensible to any future driver or
  provider) rather than a closed two-driver enum.

## Constraints that are not negotiable

- External review must stay a CLI-only, monorepo-internal surface — no webui
  change.
- The Claude-only Agent-tier resolver (ADR-127) is out of scope; nothing here
  touches Agent-tool subagent model selection.
