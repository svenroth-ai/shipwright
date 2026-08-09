# Iterate Spec: outbox-only amend delivery signal

**Status:** implemented

## Intent and scope

- **Intent:** change
- **Complexity:** medium
- **Spec impact:** MODIFY — FR-01.14 gains a visible delivery fact for a pending correction.
- **Affected requirement:** FR-01.14

## Problem

An amend for a tracked item can remain only in `.shipwright/triage.outbox.jsonl`.
The resolved card already reflects it, but the listing has no delivery fact for the
correction: `pendingDelivery` describes the original append and
`pendingStatusDelivery` describes a different event kind.

## Acceptance criteria

- [x] Given a whole-event-valid amend exists only in the outbox for an item whose
  append is tracked, when `triage_cli.py list --json` is read, then the resolved
  row has `pendingAmendDelivery: true` and the v2 envelope has a separate
  `undeliveredAmends` block naming the item.
- [x] Given a card has both a valid outbox status event and a valid outbox amend,
  when the listing is read, then `undeliveredDecisions` and `undeliveredAmends`
  each report that card independently; neither existing status field changes
  meaning.
- [x] Given an amend is invalid, orphaned, or targets an append still only in the
  outbox, when the listing is read, then it creates no pending-amend signal.
- [x] Given a canonically equivalent amend is present in the tracked store after a
  sweep, when the listing is read, then the pending-amend signal disappears.
- [x] Given the JSON envelope gains the top-level `undeliveredAmends` key, when a
  consumer reads the published contract, then `contractVersion` remains 2 under the additive compatibility rule and the
  handoff records the exact field meaning without changing `shipwright-webui`.

## Command Center handoff

`shipwright-webui` PR #355 already delivered amend resolution and the Edit
surface; it is out of scope here. The additive v2 contract adds:

- `pendingAmendDelivery: boolean` on every resolved open/deferred row — true when
  at least one valid, non-equivalently-tracked outbox amend targets that tracked
  append.
- `undeliveredAmends: {count, truncated, ids}` — the capped store-level view of
  the same amend-delivery fact, independent of `undeliveredDecisions`.

A separate WebUI card is needed only if the product needs a visible badge or label
for this newly exposed field.

## Out of scope

- Do not widen or rename `pendingStatusDelivery` / `undeliveredDecisions`.
- Do not rebuild amend resolution, change the Command Center, or add its Edit UI.
- Do not reimplement P2.52 decision-drop scanning: it landed in origin/main PR
  #615 before this iterate started.

## Affected boundaries

| Producer | Consumer | Format | Verification |
|---|---|---|---|
| `amend_triage_item` / outbox | `triage_cli.py list --json` | triage JSONL → v2 listing envelope | real CLI round-trip tests |

## Test completeness ledger

| Behavior | Disposition | Evidence |
|---|---|---|
| Tracked target with outbox-only amend | tested | focused shared delivery tests |
| Status and amend delivery coexist | tested | focused shared delivery tests |
| Invalid/orphan/outbox-only append is ignored | tested | focused shared delivery tests |
| Post-sweep equivalent amendment clears signal | tested | focused shared delivery tests |
| v2 row and envelope contract | tested | contract and CLI round-trip tests |
