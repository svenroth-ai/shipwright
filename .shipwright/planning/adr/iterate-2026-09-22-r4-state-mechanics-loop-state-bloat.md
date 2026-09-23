# Bloat exception — `shared/scripts/lib/loop_state.py` raised to 768-LOC

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

### Round 2 growth (757 -> 768)

Stage-2 code-review finding (medium, security): `rejected_payload_path`'s
containment assert compared `resolved_dir` (derived from the untrusted
`unit_id`) against `resolved_candidate.parent` — a traversing `unit_id`
moves both sides of that comparison together, so the assert passed
vacuously for exactly the input it existed to catch. Reachability is
bounded (needs a malformed `loop_state.json` row whose id bypassed
`campaign_graph.id_charset_ok`), but this is the same fresh code that
already hardens the sibling `attempt_id` parameter, so leaving `unit_id`
unhardened reads as an oversight, not a deliberate choice. Fixed by
anchoring the containment check against the LOOP-level root
(`runs_dir_for(state_path, loop_id)`, no `unit_id`) via `Path.is_relative_to`
instead of the unit-level directory `unit_id` itself derives. Not a new
responsibility — a security-hardening fix to a path-safety primitive
already counted above.

### Round 3 growth (768 -> 820)

Stage-3 doubt review (4 HIGH + 1 medium + 2 low against PR #790) landed three
fixes in this module, none a new responsibility — all hardening primitives
already counted above:

- **HIGH #1:** `sub_iterate_finalize_summary` refused ANY non-TERMINAL unit
  with no compatibility path for a row still carrying pre-R4 legacy
  vocabulary — live production risk the moment this PR merges, since the
  caller-side gate (`autonomous_loop.cmd_finalize`) needed a docstring making
  the precondition explicit for any future direct caller.
- **HIGH #2 (second half) + LOW #2:** `_reconcile_legacy` (this module,
  reused for `kind == "sub_iterate"` rows since Round 1's own fix above) wrote
  a legacy `"complete"` string into a `sub_iterate` row instead of mapping
  onto the 9-state vocabulary (`"merged"`, TERMINAL), and unconditionally
  double-bumped `attempt` on its pending fallback even though `_claim_unit`
  (`loop_claim.py`) already bumps it once on the row's actual next claim.
  Both fixed with an `is_sub_iterate` branch inside the same function — no
  new function, no new file.
- **HIGH #2 (first half):** `is_legal_transition`'s `forced=True` exemption
  required BOTH `from_state`/`to_state` to be real `STATES` members,
  contradicting its own docstring's "may cross any edge" — a row on a legacy
  `from_state` could never use the one documented operator escape hatch.
  Fixed by checking `to_state` unconditionally and `from_state` only when
  `forced` is `False` — three lines changed, same function.

### Round 4 growth (820 -> 827)

Scoped orchestrator-level re-review of Round 3's own fixes (see the sibling
`iterate-2026-09-22-r4-state-mechanics-loop-claim-bloat.md`'s Round 4 entry
for the companion `loop_claim.py` fix from the same pass) found one further
real defect in `_reconcile_legacy`, not a new responsibility: its HIGH #2
fix (above) mapped a legacy `"in_progress"` row's found `result.json` onto
`unit["merged_commit"] = result.get("commit")` unconditionally — but that
commit is a pre-merge branch tip (this reconciliation path only fires for a
row whose session died before `cmd_record`, which is always before
`campaign-mode.md` step 3g's merge), and this module's own docstring
requires every `merged_commit` write to go through
`verify_merged_commit_ancestry` first (see this file's `## Context` above)
so a rewritten/never-merged commit cannot silently satisfy a dependency
edge. Fixed by routing both `_reconcile_legacy` write sites (the
`result.json` path and the legacy branch-log fallback) through that same
verification call — two call sites, no new function.

### Round 5 growth (827 -> 861)

External Tier-3 review (GPT, high, PR #790) found Round 4's own fix
incomplete: it routed `merged_commit` through `verify_merged_commit_ancestry`
but left `unit["status"] = done_status` unconditional in both
`_reconcile_legacy` write sites — an unverified pre-merge branch tip still
flipped the row to TERMINAL `"merged"`, which is the exact false completion
`sub_iterate_finalize_summary`/campaign-mode step 3h would then publish as
done, not merely an unset field. Fixed by gating the status transition
itself on verification succeeding at both sites (`result.json` and the
branch-log fallback); an unverified commit now falls through to the
branch-log check and, failing that, the existing reset-to-pending fallback
— the same "stays blocked, never wrongly unblocked" direction this module's
own docstring already requires. Not a new responsibility — a correctness
fix to the verification primitive Round 4 already counted, plus one new
regression test proving the unverified case no longer marks the row merged.

### Round 6 growth (861 -> 877)

External Tier-3 review (GPT, high, PR #790) found `rejected_payload_path`'s
loop-root containment check insufficient on its own: a `unit_id` such as
`"A/../B"` never escapes `runs/{loop_id}/` at all (it resolves to the
sibling `runs/{loop_id}/B/`, still relative to the loop root), yet still
redirects a rejected payload meant for unit A into unit B's own real
`rejected/` directory, overwriting its file. Fixed by charset-rejecting any
`unit_id` outside `campaign_graph.id_charset_ok` up front — the same bar
`campaign_init.py` already enforces on `campaign_slug`/`slug` at write
time — before any path is built, with the loop-root check kept as
defense-in-depth. `enforce_record_fencing`'s own call site now catches the
resulting `ValueError` and fails closed with a clean exit 1 instead of an
uncaught traceback. Not a new responsibility — a completeness fix to a path
helper this module already owned; one existing test's assertion updated to
match the new (earlier, more specific) rejection reason, plus one new test
for the redirect shape the loop-root check alone missed.

### Round 7 growth (877 -> 886)

External Tier-3 review (GPT, high, PR #790) found `cmd_init_sub_iterate_payload`'s
final `if units:` fallback reported `{"action": "resumed", "pending": 0}` for
ANY non-empty unit list not already caught by the active/legacy-active/resumable
branches above it — including pre-R4 legacy terminal statuses (`"complete"`,
`"failed"`, `"escalated"`) that were never verified TERMINAL under the new
9-state vocabulary. `"escalated"` specifically means unresolved human action,
not done, so silently reporting it as resumed/nothing-pending would hide that
from the caller. Fixed by requiring `all(u["status"] in TERMINAL for u in
units)` before returning the resumed payload; anything else (empty list or a
mix containing an unrecognized legacy status) now falls through to `{}`, the
same real-reinit signal `kind == "section"` has always used for a fully-done
state. Not a new responsibility — a correctness fix to the compatibility
branch Round 4 already counted, plus one new regression test proving a
pre-R4 campaign with legacy terminal/escalated rows reinitializes rather than
reporting a false `resumed, pending: 0`.

### Round 8 growth (886 -> 919)

External Tier-3 review (GPT, high, PR #790) found `runs_dir_for` and
`handoff_dir_for` still trusted the persisted `loop_id` directly as a Path
component, with no charset validation and no containment check — unlike
`rejected_payload_path`'s already-hardened `unit_id` handling (Round 6). A
real `loop_id` is always internally minted (`f"{kind}-{timestamp}"`, always
inside the safe charset), but a hand-edited or corrupted state file could
carry anything, and both helpers would build a path from it unconditionally.
Fixed by applying the same `campaign_graph.id_charset_ok` charset check plus
a resolved-path containment assert to both functions, mirroring
`rejected_payload_path`'s existing two-layer pattern. Not a new
responsibility — a completeness fix extending Round 6's own charset-hardening
principle to the two sibling path helpers it didn't yet cover.

`handoff_dir_for`'s first draft of this fix (886 -> 913) computed a separate
`shipwright_root` variable and chained `"planning"` off of THAT instead of
directly off a `.shipwright` literal — breaking the same artifact-path-canon
AST/text-regex lint this function's own docstring already warned about,
caught by real CI (Windows + Linux `Shared tests`) rather than locally.
Fixed by keeping `.shipwright` and `"planning"` chained in one expression for
the returned path, computing the separate containment-check variable from a
DIFFERENT, non-"planning"-bearing sub-expression instead (913 -> 919).

### Round 9 growth (919 -> 939)

External Tier-3 review (GPT, high, PR #790) found `runs_dir_for` charset-
checked `loop_id` (Round 8) but appended its optional `unit_id` argument
completely unvalidated — a persisted unit row's `id` is the same
untrusted-input threat model as `loop_id`, and two callers in
`autonomous_loop.py` (`cmd_record`'s fallback-path lookup and its
result-path write) pass a raw `args.unit`/`unit["id"]` straight through.
`A/../B` in particular defeats a naive containment check alone — it
resolves to the sibling `runs/{loop_id}/B/`, which IS inside the loop
root — so the charset check (not containment) is load-bearing here, the
same realization `rejected_payload_path` already recorded for this exact
shape (Round 6). Fixed by charset-checking `unit_id` the same way
`loop_id` already is, plus a resolved-path containment re-check run AFTER
`unit_id` is appended (the existing `loop_id`-only containment check runs
before that append and cannot see a traversal introduced by `unit_id`
itself). Not a new responsibility — completing the same guarantee Round 8
already gave `loop_id`, for the sibling argument this function always
accepted but never checked.

## Consequences

- Every downstream campaign-dag-scheduler sub-iterate (R5a, R5b, R6) that
  touches `loop_state.py` operates against the current 939-line ceiling
  (see Round 9 growth above), not 278 — the next crossing needs its own ADR.
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
  (reconcile).** Rejected — but not on a bare module-count argument:
  correction (spec-reviewer re-check, 2026-09-23) — an earlier draft of
  this bullet argued this split "contradicts the plan's own explicit,
  named module assignment for this sub-iterate ... — not three", citing
  the Scope section's "two new modules" prose as if it capped the sub-
  iterate's internal module count. That framing does not survive contact
  with the sub-iterate spec's own Acceptance Criteria (the more specific,
  actually-binding gate; see
  `.shipwright/planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/R4-state-mechanics.md`
  § Acceptance Criteria), which explicitly PERMITS splitting a module
  further "if the exception would otherwise be needed purely from feature
  count, not genuine cohesion" — and this same sub-iterate exercises
  exactly that permission elsewhere, splitting `loop_claim.py` into
  `loop_claim.py` + `loop_mark.py` (see that module's own docstring). The
  Scope section's "two new modules" language describes the extraction
  target relative to `autonomous_loop.py`, not an exhaustive cap on every
  module this sub-iterate may create. The REAL reason this particular
  candidate split is rejected is the Ousterhout argument above: it buys no
  real encapsulation — `ACTIVE`/`RESUMABLE`/`STATES` would need to be
  imported right back into whichever module got `reconcile_in_progress`,
  so the "split" is really just moving the file boundary, not removing a
  dependency or separating two independently-varying concerns. That is the
  same cohesion test the AC's permission invokes; this candidate fails it,
  while the `loop_claim.py`/`loop_mark.py` split (scheduling decisions vs.
  identity-checked mutations — a real behavioral seam) passes it. Module
  count alone was never the test.
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
