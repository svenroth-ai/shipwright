# Anchor Layers-promotion to the newest verified ancestor

## Context

`promote_required_layers.py` (P3.5) only promotes an FR's required layers
when `resolve_ci_verification(HEAD)` returns `verified` — CI's fresh,
zero-drift regeneration check on `test-traceability.json` passing for
HEAD itself. Measured on 2026-09-10: PR #707 refreshed the manifest and
produced this repo's first ever `verified` HEAD; one hour and two merged
PRs later (both adding tests, which change the collected-test-ID diff
`_structural_view()` compares) HEAD was back to `not_verified`. The
verified window is structurally short and DRIFTED is the steady state, so
a mechanism gated on HEAD verification rarely gets to run.

## Decision

When HEAD itself is not verified, `ci_verified_anchor.resolve_verified_anchor`
walks HEAD's first-parent history (bounded by `max_commits`/`since_days`) for
the newest ancestor `A` where `resolve_ci_verification(A) == verified`. If
found, `promote_required_layers.py` evaluates each FR's promotion against
`A`'s manifest/evidence instead of refusing outright, but ONLY for FRs whose
bound test files are provably unchanged and unstale between `A` and `HEAD`
(`promotion_evidence_staleness.evidence_stale_since_anchor`). A promoted FR's
ledger entry records `anchor_commit` beside `ci_run_id` so the assertion's
provenance is auditable. `unavailable` (no verified commit in bound) and
`error` (git/CI-query fault, including 5+ consecutive query errors — a
circuit breaker) both degrade to "promote nothing," never a fatal exit or a
false promotion. The anchor's own execution-evidence read failing also
degrades the same way (reversed mid-iterate after doubt-review: most
`error` returns are transient query faults, not integrity signals).

`evidence_stale_since_anchor` closes two doubt-reviewed gaps beyond the
original bound-test-file diff: (1) it re-verifies the FR's manifest-node
identity at `A` vs `HEAD`, not just changed paths, and (2) it treats ANY
new test-shaped path changed in `A..HEAD` that isn't yet bound to any FR in
either manifest as invalidating — closing the "manifest not regenerated
after a new test lands" blind spot the anchor path structurally has (the
direct/tip path is protected by CI's own regen-and-diff gate; the anchor
path is not, since HEAD itself was never verified).

## Consequences

Promotion now fires on realistic timescales (anchor windows measured in
days across normal PR cadence, not the ~1-hour direct-verification window)
without loosening `resolve_ci_verification`'s unforgeability predicate
(`event==push && head_branch==default_branch && conclusion==success`) —
the anchor path adds staleness re-verification precisely because it lacks
the direct path's fresh-regeneration guarantee, rather than borrowing that
guarantee where it doesn't hold. The existing tip-verified path is
unchanged; all 34 pre-existing `promote_required_layers.py` behaviors
regression-tested green.

## Rejected alternatives

- **A — refresh/merge/promote ritual** (manifest refresh PR, pause merges,
  promote, resume): interim-only. A refresh PR touches 100%-generated
  paths, so it needs a manual admin override every cycle (`trg-a99ee30d`).
- **C — close the drift loop automatically** (a bot with default-branch
  write access that refreshes the manifest on every merge): refused three
  times across this campaign — no PAT, no dedicated CI job for one file,
  and no weakening of the "Actions cannot create PRs" org policy. Off the
  table again here, not re-litigated.

## Doubt-review disposition (Stage 3)

See the iterate spec's own `## Doubt Review` section for the full 7-item
adversarial pass: 4 findings fixed (FR-identity check, unaccounted-test-path
widening, anchor-evidence-error degrade reversal, 5x-consecutive-error
circuit breaker + case normalization), 2 deliberately deferred with
documented reasoning (narrow residual risk, not a safety gap), 1 investigated
and found already correct (no fix needed).
