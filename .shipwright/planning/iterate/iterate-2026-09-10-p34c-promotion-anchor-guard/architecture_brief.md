# Architecture Brief: Anchor Layers-Promotion to the Newest Verified Ancestor

## The problem

`promote_required_layers.py` only promotes a requirement's `Layers` binding
from inferred to explicit when the exact HEAD commit is itself CI-verified.
Measured on this repo: a verified window opened for about one hour before
closing structurally (any PR touching test files changes the traceability
manifest's comparison), and nothing may un-drift `main` outside a separate
manual refresh PR. With multiple iterates in flight, "verified" is the
exception rather than the norm, so the mechanism rarely gets a chance to run
at all.

## What already exists here

- `resolve_ci_verification` — the sole unforgeability predicate (a `push`,
  default-branch, green CI run at the exact commit). Unmodified by any option
  below.
- `resolve_execution_evidence` — composes with the predicate above to fetch
  and content-bind a CI-produced per-FR test/coverage artifact to one exact
  commit.
- `lib.layer_promotion.evaluate_fr` — the pure per-requirement promotion
  decision function, given whatever evidence it is handed.
- An append-only promotion ledger recording every promote/skip/escalate
  decision with its evidence provenance.

## What would newly, permanently exist

A bounded first-parent ancestor walk that finds the newest CI-verified
commit when HEAD itself is not verified, plus a per-requirement staleness
guard that refuses to reuse that ancestor's evidence for any FR whose bound
test files or spec.md changed between the ancestor and HEAD. Both run inside
every future invocation of `promote_required_layers.py` from now on, and
maintainers extending that tool must account for the anchor/staleness path
alongside the existing tip-verified path.

## Options on the table

- **A:** Manual ritual — refresh the traceability manifest, merge nothing
  else, then run the promotion tool while the tip is momentarily verified.
- **B:** Anchor promotion decisions to the newest CI-verified ancestor commit
  reachable from HEAD, gated by a per-requirement staleness check against
  that ancestor.
- **C:** A bot with write access to the default branch that keeps the
  traceability manifest continuously refreshed and verified.

## Constraints that are not negotiable

`resolve_ci_verification`'s trust boundary (`event==push`,
`head_branch==default_branch`, `conclusion==success`) must not change or
weaken under any option. No option may grant any automation write access to
the default branch outside the existing PR-and-review path.
