# Deferred: split-or-ADR decision for the two H1 bloat outliers

## Context

The 2026-09-25 H1 drift sweep found 28 files that had grown past the 300-line
limit without being recorded in `shipwright_bloat_baseline.json`. This run
(`iterate-2026-09-28-compliance-hygiene-f6-h1`) merged 26 of them into the
baseline as `state: "grandfathered"` via the baseline's own producer
(`shared/scripts/lib/bloat_baseline.py::scan`) — the schema's designed default
for "this-is-where-we-started" debt, distinct from the ADR-gated `"exception"`
state. Every pre-existing entry (250 of them) was left byte-for-byte
untouched. See the run's ADR (`--run-id
iterate-2026-09-28-compliance-hygiene-f6-h1`) for the full change.

Two of the 28 are extreme outliers, not ordinary drift, and are
**deliberately left out of the baseline**:

- `shared/scripts/lib/assertion_weakening.py` — 1676 lines (5.6x the limit)
- `shared/tests/test_assertion_weakening.py` — 1509 lines (5x the limit)

`H1` (`plugins/shipwright-compliance/scripts/audit/group_h.py`) therefore
still correctly reports these two as open. This is intentional, not an
oversight — see "Decision" below.

An earlier operator note on a related, smaller H1 card (`trg-0801c0a8`,
2026-09-11) was explicit that bulk-baselining should not be used to paper
over a file this far outside the limit — it called for "a decision per file
between an ADR-backed baseline exception and a split," singling out
`assertion_weakening.py` by name as deserving its own look rather than a
formality. This run's first attempt at closing H1 grandfathered these two
files anyway (with a `note` field flagging the deferred decision); the PR's
automated Tier-3 review correctly caught that this reproduced exactly the
pattern the operator had rejected — grandfathering removes the file from the
H1 finding without doing the work the note admits is still owed — and
blocked the PR on it. This revision removes the two entries from the
baseline instead, so H1 stays open for them until the real decision is made.

## Decision

This run does **not** make that per-file design decision, and does **not**
launder it through the baseline either. Splitting a 1676-line module (and its
1509-line test file) safely — picking real seams, keeping every test green,
without design context on why the file grew this large — is not something to
rush inside a single autonomous compliance-hygiene pass whose actual scope is
two mechanical findings (F6, H1). Leaving H1 open for exactly these two files
keeps the compliance signal honest: the finding is not closed until one of
the two options below actually happens.

## What's still owed

A dedicated follow-up (iterate or short campaign) should read
`shared/scripts/lib/assertion_weakening.py` and its test, and pick one of:

- **Split** — identify real seams (the file's own docstring/section
  structure is the first place to look) and break it into cohesion-driven
  modules under the 300-line limit. This closes H1 for these two files with
  no baseline entry needed at all.
- **ADR-backed exception** — if the file's size is a deliberate, justified
  design choice (e.g. a single cohesive state machine that resists splitting),
  record that as a `state: "exception"` baseline entry with a real ADR
  reference, per `shared/glossary.md`'s Allowlist/Anti-Ratchet rules. Only
  this — not `grandfathered` — is the legitimate way to close H1 for a file
  this far outside the limit without splitting it.

The 5 files from the P3.3/P3.5 layer-promotion family the 2026-09-11 note
also flagged as having "arrived together" (`layer_promotion.py`,
`layer_promotion_ledger.py`, `fr_layer_cell_writer.py`,
`record_layer_promotion_decision.py`, `ci_execution_evidence.py`) are much
closer to the limit (1.2-1.4x, vs. 5-5.6x for the pair above) and were
grandfathered by this run along with the other ordinary drift — the
Tier-3 review did not object to that. Revisit them too if a future pass is
already in that code.
