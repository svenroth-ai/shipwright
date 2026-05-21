# Iterate Spec: C.1 — Hard-enforce FR-or-change-type at finalize

- **Run ID:** iterate-2026-05-21-c1-fr-gate-finalize
- **Type:** feature
- **Complexity:** small
- **Status:** draft

## Goal

Close the artifact-polish plan's Iterate C.1 by hard-enforcing
forward-only that every iterate's `work_completed` event records
positive classification: either the FR(s) it touched, OR a
`change_type` from a small fixed vocabulary together with a one-line
`none_reason`. Phase 0 of the campaign already classified every
pre-existing event, so this hard-enforcement is risk-free in the
monorepo + webui.

## Acceptance Criteria

- [ ] **AC-1** New private predicate
  `record_event._fr_or_change_type_gate_error(event)` returns an
  error payload `{"error": "fr_gate_unclassified", "detail": "..."}`
  iff the event needs classification and lacks it. Pure function,
  no I/O, easy to unit-test.

- [ ] **AC-2** The gate fires only for
  `event["type"] == "work_completed" AND event["source"] == "iterate"`.
  Build events and all non-work_completed events bypass.

- [ ] **AC-3** Pass conditions (any one):
  - `affected_frs` non-empty list, OR
  - `new_frs` non-empty list, OR
  - `change_type` ∈ {`docs`, `tooling`, `compliance`, `infra`} AND
    `none_reason` is a non-empty trimmed string.

- [ ] **AC-4** Reject conditions (all others):
  - missing both FR fields AND missing `change_type`, OR
  - `change_type` set but `none_reason` empty / whitespace-only, OR
  - `change_type` set to a value outside the allowed set (defense
    in depth — argparse `choices` already rejects this at the CLI
    layer).

- [ ] **AC-5** Gate runs BEFORE `_spec_impact_gate_error` in `main`,
  so the broader requirement surfaces first.

- [ ] **AC-6** Hard-fail behavior: `main` prints
  `{"success": false, "error": "fr_gate_unclassified", "detail": "..."}`
  on rejection, exits 1, and writes NOTHING to
  `shipwright_events.jsonl`.

- [ ] **AC-7** Read-side stays tolerant — events written before this
  gate landed continue to parse via the existing optional fields
  (`change_type`, `none_reason` already on the read-side schema as
  of the artifact-polish Phase 0 prep). No schema break.

- [ ] **AC-8** SKILL.md F7 documentation explains the new gate
  alongside the existing spec-impact gate, including the BUG-
  iterate path (`--change-type tooling --none-reason "..."`).

## Out of scope

- **`spec_impact` gate refactor** — kept untouched. The two gates
  enforce different things (FR vs spec-impact classification) and
  can coexist.

- **`event.schema.json` JSON-Schema file** — `change_type` /
  `none_reason` are already optional on the wire (Phase 0 prep);
  a formal JSON-Schema file for `event` is out of scope here and
  remains future work.

- **Retroactive enforcement on the existing event log** — the gate
  is forward-only (every NEW event from this iterate onward).
  Historical events are read-tolerant; the on-demand
  `/shipwright-compliance` audit Group D can flag historical gaps
  if needed.

- **`shipwright-compliance` Group D audit extension** — a future
  iterate could add a `D6` check that surfaces historical iterates
  without classification. Not in C.1 scope.

## Implementation Notes

- The gate predicate is a 25-line pure function with explicit
  return paths for "bypass", "pass via FRs", "pass via change_type
  + reason", and "fail". No early-return chain — explicit branches
  match the test matrix one-to-one.

- The order of gates in `main` matters: FR-gate first because it's
  the broader requirement (every iterate, including BUG); spec-
  impact gate second because it's stricter for FEATURE/CHANGE only.

- The existing `--change-type` CLI flag has `choices=["docs",
  "tooling", "compliance", "infra"]` so a bad value never reaches
  the event dict via the CLI path; the gate still rejects bad
  values for defense in depth (in case a producer constructs the
  event dict directly via `build_event`).

- BUG iterates that fix bugs tied to an FR set `--affected-frs`;
  BUG iterates that fix internal tooling set `--change-type
  tooling --none-reason "<reason>"`. Both paths pass.

## Verification

- `uv run --extra dev pytest shared/tests/test_record_event.py
  -v -k FrOrChangeTypeGate` — 13 new tests covering AC-1..AC-7.

- Full shared suite: 2129 passed (baseline 2116 + 13 new).

- `uv run --extra dev pytest plugins/shipwright-compliance/tests/`
  → 410 maintained (no compliance changes in C.1).

- `uv run --extra dev pytest shared/tests/test_finalize_iterate.py`
  → existing tests still pass (the gate fires before finalize_iterate
  reads anything, so finalize's behavior is unchanged when the
  caller passes the right flags).
