# Architecture Brief: agent-model-tiers

## The problem

Agent definitions carry `model: inherit`, so every subagent runs on whatever
the main session runs on. When an operator switches the session down a tier
for cost, the review cascade and the two agents driving finalization
unattended follow silently, and the run still reports passed reviews with no
record of which tier they ran on. The defect is the silence, not the tier
choice itself.

## What already exists here

- Agent frontmatter `model:` field — static, per-agent, currently `inherit`
  on every agent except two long-standing pins.
- `reviews.json`, a per-run review record (`record_review_pass.py`) that
  already tracks status, findings and verdicts for every review pass.
- Per-concern `shipwright_<name>_config.json` files, each with its own
  loader (e.g. `external_review_config.py`).
- The F11 finalization verifier chain (`review_record_check.py`), which
  already has an established pattern for an advisory, non-blocking note
  appended to a passing check result.

## What would newly, permanently exist

An operator-authored config file, read at the start of every iterate/build
run; a resolver and a CLI wrapper that turn it (plus per-run flags) into a
tier per spawn role; a new optional field on the `reviews.json` review
record; and a new advisory-only F11 check reading an optional floor from the
same config. From this point on, every review/finalization/execution spawn
site in iterate and build reads through this resolver, and a future spawn
site added elsewhere is expected to follow the same pattern rather than
invent its own.

## Options on the table

- **A:** Per-run CLI flags plus an optional project-level config file,
  precedence flag > config > unset, resolved once and passed as an
  Agent-tool call parameter at each spawn.
- **B:** Hardcode a specific tier directly into the review/finalization
  agents' frontmatter.
- **C:** A single flat environment variable — one tier, no per-role split —
  read once at session start.
- **D:** Do nothing. Leave every agent on `inherit` and accept that a
  session-tier change silently affects review quality with no record of it.

## Constraints that are not negotiable

none
