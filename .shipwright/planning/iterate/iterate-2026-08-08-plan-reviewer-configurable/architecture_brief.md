# Architecture Brief: plan-reviewer-configurable

## The problem
The internal plan-review subagent's model is hard-wired to `opus` in its own
frontmatter, so a project cannot substitute a different model (e.g. a
non-Anthropic model attached via a future integration) for that one review
role, unlike the three roles a prior change already made configurable.

## What would newly, permanently exist
Nothing. This adds a fourth role to a model-tier resolution mechanism that
already exists (`shipwright_model_config.json` / `resolve_model_tier.py`,
covering `review`/`finalization`/`execution` since 2026-08-07) and adds one
member to an already-existing, already-growing review-record type vocabulary
(`REVIEW_TYPES`, currently six members).
