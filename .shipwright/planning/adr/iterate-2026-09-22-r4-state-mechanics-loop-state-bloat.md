# Bloat exception — `shared/scripts/lib/loop_state.py` raised to 757-LOC

<!-- Named by run_id per `_template-bloat-exception.md` — this heading does
     NOT claim a numeric ADR-NNN; that identity is assigned later, at
     release, by decision_log.md. `shipwright_bloat_baseline.json`'s entry
     for this file is set to `"state": "exception", "adr": "ADR-pending:
     .shipwright/planning/adr/iterate-2026-09-22-r4-state-mechanics-loop-state-bloat.md"`. -->

- **Status:** accepted
- **Date:** 2026-09-22
- **Re-Review-Date:** 2026-12-22
- **Incident Reference:** `iterate-2026-09-22-r4-state-mechanics` (campaign
  `campaign-dag-scheduler`, sub-iterate R4). The limit was crossed
  delivering the sub-iterate's own explicitly-specified module boundary:
  `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md`
  § "R4 — concurrent state mechanics" names `loop_state.py` as the home for
  "state machine, `_load_units_from`, lease fields, `_reconcile_in_progress`"
  — a single module, by explicit design, not an accident of scope creep.

## Context

`loop_state.py` was 278 lines after R1 (`_load_units_from`,
`verify_merged_commit_ancestry`, `is_unit_ready`, `describe_blocker` — the
`depends_on` readiness predicate and its supporting status-mapping/ancestry
logic). R4 adds, per its own spec's explicit module assignment: the 9-state
machine's edge table and `is_legal_transition`; the fencing primitives
(`validate_attempt_token`, `is_valid_sha`, `find_unit_row`) every mutator in
`loop_claim.py` and `check_unit_attempt.py` shares; the canonical
state-root path helpers (`runs_dir_for`, `rejected_payload_path`,
`handoff_dir_for` — R4 work item 11's cwd-independence fix); and
`reconcile_in_progress`, which now carries BOTH the untouched
`kind == "section"` legacy salvage path (moved here verbatim from
`autonomous_loop.py`, not duplicated — its move is what makes
`autonomous_loop.py` shrink) and the new `kind == "sub_iterate"`
lease-expiry-only reclaim. That is five cohesive, spec-assigned
responsibilities landing in one file in one sub-iterate; none is
speculative or deferrable.

**Post-external-code-review growth (668 → 742):** the external code-review
cascade (OpenAI, high + medium) found a real TOCTOU race in `cmd_record`'s
fencing check (a single early check, in a lock since released, was not
re-validated at write time) and a real path-traversal risk in
`rejected_payload_path` (an untrusted `--attempt-id` reaching an f-string
path segment). Both fixes belong in this module (the fencing/path-safety
primitives already live here) — `enforce_record_fencing` gained a
`target_status` legality check re-run inside every write lock, and
`rejected_payload_path` gained a charset-validated/digest-fallback filename
plus a resolved-path containment assert. Neither is a new responsibility;
both harden ones already counted above.

**Post-external-code-review growth, second pass (742 → 757):** the GLM half
of the same code-review cascade (high) found that `cmd_init_sub_iterate_payload`
never accounted for the pre-R4 legacy status `"in_progress"` — still the live
status `autonomous_loop.cmd_next` writes for `--branch-strategy serial`
sub_iterate campaigns — leaving such a unit invisible to the new
ACTIVE/RESUMABLE/TERMINAL partition and silently reported as
`{"action": "resumed", "pending": 0}` despite being genuinely stuck. Fixed by
routing any `"in_progress"` unit through the untouched `_reconcile_legacy`
path alongside (not instead of) the new lease-based reconcile for ACTIVE
units — a fix to an existing responsibility (the `cmd_init` resume/reinit
decision body), not a new one.

## Ousterhout Argument

`loop_state.py`'s entire public surface is a set of small, independent pure
(or nearly-pure) functions over one shared vocabulary — a `loop_state.json`
unit row and its 9-state lifecycle. Every consumer (`autonomous_loop.py`,
`loop_claim.py`, `check_unit_attempt.py`, three plugin-side reference docs)
imports two or three of these functions and never needs to know how any of
them are implemented — `is_legal_transition` hides the whole edge table,
`reconcile_in_progress` hides two entirely different reconciliation
strategies behind one `kind` dispatch, `runs_dir_for` hides the
state-root-anchoring logic. This is the textbook "narrow interface, deep
implementation" shape a bloat split would break: splitting the state-machine
constants from the reconcile functions that consume them (`ACTIVE`,
`RESUMABLE`, `STATES` are read by both `autonomous_loop.cmd_init` and
`reconcile_in_progress`) would either duplicate the vocabulary across two
files or force a third module whose only job is re-exporting — the ADR-045
lib-collision risk this campaign has repeatedly hardened against, for zero
behavioral benefit. The module's own name — `loop_state`, not
`loop_state_machine` or `loop_reconcile` — already promises "everything
about a unit's state," which is exactly what all five responsibilities are.

## YAGNI Check

- The 9-state machine + edge table: needed today — `loop_claim.py`'s every
  mutator (this same sub-iterate) calls `is_legal_transition`, and
  `autonomous_loop.cmd_init`'s `ACTIVE`/`RESUMABLE` gating needs the same
  vocabulary. Not speculative.
- The fencing primitives (`validate_attempt_token`, `is_valid_sha`,
  `find_unit_row`): needed today by `cmd_record`'s new fencing gate,
  `check_unit_attempt.py` (new CLI, same sub-iterate), and
  `loop_claim.py`'s `cmd_mark_running`/`cmd_mark_merged`. Not speculative.
- The state-root path helpers: needed today — work item 11 is an explicit
  AC of this sub-iterate, not a future nice-to-have.
- `reconcile_in_progress`'s `kind == "section"` branch: NOT new
  responsibility — it is `autonomous_loop._reconcile_in_progress` MOVED, not
  grown. Leaving it duplicated in both files instead of moved was
  considered and rejected below.
- No responsibility here could be deleted today without breaking this same
  sub-iterate's own acceptance criteria.

## Chesterton-Fence Check

`loop_state.py` already carries R1's `_load_units_from` and
`verify_merged_commit_ancestry` for exactly this "coherent, independently
testable unit" reason — that module's own docstring (predating this ADR)
already states the fence: "these ... are a coherent, independently testable
unit, and living together means [a caller's] signature can genuinely
mirror [another]'s ... without a new shape". R4 does not tear down that
fence; it is the SAME design principle applied to the next layer of this
module's stated charter (the plan document's own module assignment,
verbatim, predates this diff). No undocumented historical reason was found
suggesting this file should instead be split — the opposite: the plan
explicitly assigns this scope to one file, by name, before any line of R4
code existed.

## Decision

Raise `current` for `shared/scripts/lib/loop_state.py` from **278 to 757**,
`state: "exception"`, `adr: "ADR-pending:
.shipwright/planning/adr/iterate-2026-09-22-r4-state-mechanics-loop-state-bloat.md"`,
in the same commit as this sub-iterate's build. **Retirement plan:**
re-review at 2026-12-22 whether R5a/R5b's own work (which reads this
module's fencing/reconcile primitives extensively) reveals a natural,
non-duplicating second module boundary — e.g. if the reconcile functions
grow further with drain-sweep logic (`reason_code` producers), that growth
alone may justify splitting reconcile out from the state-machine/fencing
core at that point, once there is a second real consumer shape to design
the boundary around rather than guessing one now.

## Consequences

- Every downstream campaign-dag-scheduler sub-iterate (R5a, R5b, R6) that
  touches `loop_state.py` operates against the new 757-line ceiling, not
  278 — the next crossing needs its own ADR.
- No test file needed its own bump: all new tests for this sub-iterate's
  additions live in `shared/tests/test_loop_state_transitions.py` (state
  machine + reconcile dispatch), `shared/tests/test_loop_state_fencing.py`
  (fencing primitives, path helpers, init/finalize/record-status bodies —
  split from the former purely to keep each file under the 300-line
  guideline), and `shared/tests/test_loop_claim.py` / `test_loop_mark.py`
  (the new CLIs); none of these existed before this diff, so none carries
  baseline history to ratchet.

## Rejected alternatives

- **Split into `loop_state.py` (load/verify/readiness) +
  `loop_transitions.py` (state machine/fencing) + `loop_reconcile.py`
  (reconcile).** Rejected: contradicts the plan's own explicit, named
  module assignment for this sub-iterate ("mechanics go into two new
  modules — `loop_state.py` ... and `loop_claim.py`" — not three), and
  the Ousterhout argument above shows the split buys no real encapsulation
  — `ACTIVE`/`RESUMABLE`/`STATES` would need to be imported right back into
  whichever module got `reconcile_in_progress`, so the "split" is really
  just moving the file boundary, not removing a dependency.
- **Leave `_reconcile_in_progress`'s `kind == "section"` branch in
  `autonomous_loop.py` and only add the new `kind == "sub_iterate"` branch
  to `loop_state.py`.** Rejected: this is exactly the two-copies-of-one-
  dispatch shape the module docstring's own opening paragraph warns
  against — `autonomous_loop.cmd_init` would need to call two different
  functions from two different modules depending on `kind`, coupling its
  own dispatcher to the same distinction this module already owns, and
  `autonomous_loop.py`'s own bloat ceiling has zero headroom to keep
  either branch resident there.
- **File no exception; let the post-merge Group H detective audit surface
  it.** Rejected: the crossing is certain and immediate (757 vs. limit 300),
  not a maybe — filing now, in the same diff, is the documented
  anti-ratchet-compliant path (mirrors this same campaign's R2 precedent
  for `autonomous_loop.py`), and leaving a known crossing unfiled for a
  future audit to discover is not an actual disposition.
