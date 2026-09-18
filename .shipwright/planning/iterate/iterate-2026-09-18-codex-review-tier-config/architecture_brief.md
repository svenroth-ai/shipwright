# Architecture Brief: codex-review-tier-config

## The problem

Two model-tier axes in the internal review cascade are stale by
construction. The Codex-side reviewer identity is a single hardcoded model
name with no way for an operator to change it. The Claude-side reviewer tier
list is a hand-maintained set of four names that has already missed a fifth,
already-valid name without anyone noticing until it was checked directly
against the running tool.

## What already exists here

- A Claude-side project-config + per-run-override mechanism for
  `review`/`plan_review` tiers (`shipwright_model_config.json` +
  `model_tier_config.py` + CLI flags), already in production use.
- A single hardcoded Codex reviewer model, injected into a `codex exec`
  subprocess call, with no config or override surface.
- A separate, similarly hardcoded Codex model identity used for a different
  purpose (external second-opinion review), already config-driven and
  independently locked from the internal-review one.

## What would newly, permanently exist

A second, independent config axis (two new optional keys in the existing
`shipwright_model_config.json`) and a small module that queries the Codex
CLI's own model-listing subcommand to validate a configured or overridden
value before it is used, with a fallback path for when that query cannot be
made. From now on, whoever changes what models Codex reviewers can be
pointed at maintains this axis and its validator, the same way the existing
Claude-side axis is already maintained today.

## Options on the table

- **A:** Give the Codex reviewer identity its own config + override axis,
  validated against a live query of Codex's own model list.
- **B:** Leave the Codex reviewer identity as a single hardcoded constant;
  only fix the Claude-side tier list's missing entry.
- **C:** Fold Codex's model choice into the same closed enum the Claude tier
  axis already uses, adding named Codex models as more literals in that one
  list.
- **D:** Do nothing; leave both axes as they are today.

## Constraints that are not negotiable

- The Codex CLI's own model-listing subcommand is the only way to check
  which model names are currently valid for that provider — there is no
  equivalent for the Claude side, which has no externally queryable
  enumeration of the aliases its own harness accepts.
- Whatever is built must not change behavior for a project that configures
  nothing — the change is additive to two existing, already-shipped review
  mechanisms.
