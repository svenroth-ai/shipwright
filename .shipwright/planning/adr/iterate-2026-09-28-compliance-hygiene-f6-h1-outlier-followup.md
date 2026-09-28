# Deferred: split-or-ADR decision for the H1 bloat outliers

## Context

The 2026-09-25 H1 drift sweep found 28 files that had grown past the 300-line
limit without being recorded in `shipwright_bloat_baseline.json`. This run
(`iterate-2026-09-28-compliance-hygiene-f6-h1`) closed H1 by merging all 28
into the baseline as `state: "grandfathered"` via the baseline's own producer
(`shared/scripts/lib/bloat_baseline.py::scan`) — the schema's designed default
for "this-is-where-we-started" debt, distinct from the ADR-gated `"exception"`
state. Every pre-existing entry (250 of them) was left byte-for-byte
untouched; only the 28 missing paths were added. See the run's ADR
(`--run-id iterate-2026-09-28-compliance-hygiene-f6-h1`) for the full change.

Two of the 28 are extreme outliers, not ordinary drift:

- `shared/scripts/lib/assertion_weakening.py` — 1676 lines (5.6x the limit)
- `shared/tests/test_assertion_weakening.py` — 1509 lines (5x the limit)

An earlier operator note on a related, smaller H1 card (`trg-0801c0a8`,
2026-09-11) was explicit that bulk-baselining should not be used to paper
over a file this far outside the limit — it called for "a decision per file
between an ADR-backed baseline exception and a split," singling out
`assertion_weakening.py` by name as deserving its own look rather than a
formality.

## Decision (deferred, deliberately)

This run does **not** make that per-file design decision. Splitting a
1676-line module (and its 1509-line test file) safely — picking real seams,
keeping every test green, without design context on why the file grew this
large — is not something to rush inside a single autonomous compliance-hygiene
pass whose actual scope is two mechanical findings (F6, H1). Grandfathering
here only restores the anti-ratchet's visibility (the file can no longer grow
further undetected); it does not certify the size as acceptable.

Both baseline entries carry a `note` field pointing at this file so the
question is not silently lost.

## What's still owed

A dedicated follow-up (iterate or short campaign) should read
`shared/scripts/lib/assertion_weakening.py` and its test, and pick one of:

- **Split** — identify real seams (the file's own docstring/section
  structure is the first place to look) and break it into cohesion-driven
  modules under the 300-line limit.
- **ADR-backed exception** — if the file's size is a deliberate, justified
  design choice (e.g. a single cohesive state machine that resists splitting),
  record that as a `state: "exception"` baseline entry with a real ADR
  reference, per `shared/glossary.md`'s Allowlist/Anti-Ratchet rules.

Either resolution should also reconsider the 5 files from the P3.3/P3.5
layer-promotion family the 2026-09-11 note flagged as having "arrived
together" (`layer_promotion.py`, `layer_promotion_ledger.py`,
`fr_layer_cell_writer.py`, `record_layer_promotion_decision.py`,
`ci_execution_evidence.py`) — all five are now also baselined
(`grandfathered`) by this run, for the same reason.
