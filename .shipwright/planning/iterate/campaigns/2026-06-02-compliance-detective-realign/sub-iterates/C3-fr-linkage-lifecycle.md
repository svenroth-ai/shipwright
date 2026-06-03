# C3 — FR-linkage lifecycle (FR-gate finalize bypass + D3 semantics)

- **Type:** change (write-gate + check-semantics)
- **Complexity:** medium (write-path change has higher blast radius — gate can
  block iterate finalize)
- **Repo:** monorepo (`shared/scripts/tools/record_event.py`,
  `…/finalize_iterate*`, `plugins/shipwright-compliance/scripts/audit/group_d.py`)
- **Depends on:** — (reopen-write-path trace RESOLVED 2026-06-02, see below)
- **Closes:** D3 of `trg-2bce4cc6`; prevents recurrence of D5-class

## Problem

Two halves of the same FR-linkage lifecycle are wrong:

- **Preventive gap (D5-class).** The FR-gate
  `record_event._fr_or_change_type_gate_error` (ADR-059, Iterate C.1) hard-rejects
  a `source=iterate` `work_completed` feature/change event that has neither FRs
  nor a valid `change_type`+`none_reason`. The reopen event `evt-83b9b73f`
  (`feature`, `spec_impact=ADD`, none of the above) is exactly that shape, yet it
  is in the log — because the gate runs only at the `record_event.main` CLI
  boundary, and `finalize_iterate._record_event` writes via `append_event`
  **bypassing the gate** (docstring: "Tightening that path is out of scope for
  C.1"). So D5 (detective) catches what the gate should have prevented at F5.
- **Detective over-strictness (D3).** `group_d._check_d3` requires a
  **strictly-later** `affected_frs` event (`ts > promised_ts`). A feature that
  introduces a new FR **and** delivers it in the **same** event (`FR-01.33` in
  `evt-177f8389` — the normal single-iterate case) is flagged "never reaffirmed"
  forever, until some unrelated later event happens to touch that FR.

## Goal

Make FR-linkage correct on both sides: prevent FR-less feature/change events at
**write** time (so D5 has nothing to catch going forward), and stop D3 from
flagging legitimately-delivered single-iterate FRs.

## Acceptance Criteria

- [ ] **AC-1 (gate on finalize path).** `finalize_iterate._record_event` (and any
      other `append_event` caller that writes `source=iterate work_completed`)
      runs through the same FR-gate as the CLI; a feature/change event with no FR
      and no valid `change_type`+`none_reason` is **rejected before write**.
- [ ] **AC-2 (fail-closed, no data loss).** A rejected finalize event surfaces a
      clear actionable error (which field is missing) and does **not** silently
      drop the iterate's work record — finalize halts with guidance, matching the
      CLI gate's fail-closed contract.
- [ ] **AC-3 (D3 same-event delivery).** An FR present in both `new_frs` and
      `affected_frs` of the **same** `work_completed` event counts as delivered;
      D3 only flags FRs promised via `new_frs` with **no** covering `affected_frs`
      at all (same-event or later).
- [ ] **AC-4 (D3 webui green).** Re-running the audit, `FR-01.33` is no longer D3-pending.
- [ ] **AC-5 (no preventive regression).** Existing CLI-recorded events that pass
      the gate today still pass; build (`source != iterate`) events still bypass.

## Resolved trace (2026-06-02) — exact bypass + insert point

The bypass is **`finalize_iterate._record_event`** (`shared/scripts/tools/finalize_iterate.py:186`):
it imports only `append_event, generate_event_id, read_events` and calls
**`append_event(project_root, event)` directly at line 261** — it never routes
through `record_event.main`, so `_fr_or_change_type_gate_error` never runs. The
iterate's rich `work_completed` event (intent / spec_impact / FRs) is assembled
here by merging `event_extras` into the event dict. The reopen event reached it
with `event_extras={intent:feature, spec_impact:ADD}` but no `affected_frs` /
`change_type` → written unchecked.

The "real SHA" red herring is explained: `_record_event` sets `commit or ""`
(line 250) — the F7 post-commit call (`--commit` given) stamps the SHA; the
F5b-pre calls leave `commit=""`. Same writer, different timing. Not a separate
path.

**AC-1 insert point:** call the FR-gate inside `_record_event` (before the
`append_event` at line 261) for `source=iterate` `work_completed` events. Reuse
`record_event._fr_or_change_type_gate_error` (single source of truth — do not
re-implement). The idempotency early-return (lines 222-230) must be preserved.

## Tests

- finalize writes a feature event with no FR / no none_reason → rejected (AC-1/2).
- finalize writes a feature event WITH FRs → allowed.
- D3: FR in same-event `new_frs`+`affected_frs` → not pending.
- D3: FR in `new_frs` only, never affected → still flagged.

## Risk / care

- **Highest blast radius in this campaign.** A too-aggressive finalize gate can
  block legitimate iterate completion. Bias the rejection message toward
  actionable guidance; consider a one-release warn-then-enforce ramp.
