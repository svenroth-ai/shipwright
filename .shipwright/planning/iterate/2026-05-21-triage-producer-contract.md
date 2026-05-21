# Iterate Spec: triage-producer-contract

- **Run ID:** iterate-2026-05-21-triage-producer-contract
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's Iterate B0 hard-prerequisite by codifying
the existing Triage producer contract. Three concrete deliverables:

1. **Formal JSON schema** at `shared/schemas/triage_item.schema.json` —
   makes the wire format an SSoT instead of an implicit shape baked into
   `shared/scripts/triage.py`.
2. **RTM cross-link fields** — three optional camelCase keys (`frId`,
   `suiteId`, `eventId`) so a future RTM render can emit `FAIL →
   [trg-XXX](triage_inbox.md#trg-XXX)` deep-links from a failing FR row
   directly to the matching triage card.
3. **Inbox-render polish** — anchor IDs per card (so the RTM links land)
   plus info-severity items collapsed into a `<details>` block at the
   end of `triage_inbox.md` (signal-first surface for solo dev).

Scope-scoped DOWN from the artifact-polish plan: the central producer
API and the existing 7-producer migration already shipped in
`iterate-2026-05-20-triage-launch-surface` and earlier — see
`docs/triage-inbox.md`. B0 just adds the schema file + cross-link
contract + render polish without breaking changes.

## Acceptance Criteria

- [ ] **AC-1** `shared/schemas/triage_item.schema.json` exists and is a
  valid Draft-2020-12 schema (loads cleanly via `jsonschema.Draft202012Validator`).

- [ ] **AC-2** A header line emitted by `_ensure_header()`, a minimal
  `append` event from `append_triage_item(...)`, and a `status` event
  from `mark_status(...)` all validate against the schema without errors.

- [ ] **AC-3** A maximal `append` event populating every optional kwarg
  — including the new `fr_id`, `suite_id`, `event_id` — validates against
  the schema, AND the new fields land on the wire under camelCase keys
  `frId`, `suiteId`, `eventId`.

- [ ] **AC-4** Schema-negative tests: an event with `severity="URGENT"`
  (out of enum) fails validation; an event with `id="trg-XYZ"` (malformed)
  fails validation.

- [ ] **AC-5** `aggregate_triage.py` emits an HTML anchor
  `<a id="trg-XXX"></a>` directly above each rendered card. The anchor
  is the same string as the card's `id`, so a markdown link of the form
  `[FAIL](triage_inbox.md#trg-XXX)` lands on the card.

- [ ] **AC-6** `aggregate_triage.py` partitions open items into
  `signal` (severity ∈ critical/high/medium/low) and `info`. Signal items
  render in the existing top section. Info items render inside a
  `<details><summary>Info-level items (N) — expand to view</summary>...`
  block at the end of the file.

- [ ] **AC-7** When every open item is info-severity, the top section
  still renders with a `No non-info triage items pending. ✓` line so
  the file structure stays stable for grep / diff tooling.

- [ ] **AC-8** When zero info items exist, no `<details>` block is
  emitted (no empty noise in the diff).

## Out of scope

- **Granularity decisions for SBOM-undeclared and test-FAIL producers**
  (the Open-Question #1 from the artifact-polish plan). Decisions
  recorded in the ADR spec file at
  `.shipwright/planning/adr/054-triage-producer-contract.md` for future
  reference, but B.2 / B.3 (the actual producers) will implement them.
- **Declarative `resolve_condition`** field on triage items. Today
  auto-resolve is hardcoded per-producer; B0 keeps it that way because
  the producer set is small (~7) and stable. Worth revisiting only if a
  10th+ producer appears and a pattern emerges.
- **Severity-vocabulary rename** from critical/high/medium/low/info to
  the plan's info/warn/major/minor — breaking change with no UX benefit,
  rejected.
- **Typed `entity_type` / `entity_id`** refactor that the plan suggested
  in place of today's `kind` + `title` — breaking change, no consumer
  needs it.
- **RTM-side rendering** of the `FAIL → trg-XXX` link itself — lives in
  B.4 (RTM generator polish). B0 only ships the producer-side contract
  (the wire fields + anchor IDs).

## Implementation Notes

- Schema lives at `shared/schemas/triage_item.schema.json` alongside the
  existing `run_config.v2.schema.json` and `decision_drop.schema.json`.
- `triage.py` extends the `event` dict in both `append_triage_item` and
  `append_triage_item_idempotent` with the three new optional camelCase
  keys. Null is the wire default — existing producers don't need
  changes; new producers (the eventual SBOM + test-evidence triage
  emitters in B.2 / B.3) just pass the kwargs.
- `aggregate_triage._render_item` prepends an HTML anchor; `render_markdown`
  splits via a new `_split_info_items` helper.

## Verification

- `uv run --extra dev pytest shared/tests/test_triage_schema.py` — 10
  new schema-validation tests cover AC-1 through AC-4.
- `uv run --extra dev pytest shared/tests/test_triage_aggregator.py` —
  4 new aggregator tests cover AC-5 through AC-8.
- Full shared suite green: `uv run --extra dev pytest shared/tests/`.
