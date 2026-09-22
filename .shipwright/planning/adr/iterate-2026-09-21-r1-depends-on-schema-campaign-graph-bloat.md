# Bloat exception — `shared/scripts/lib/campaign_graph.py` raised to 354-LOC

- **Status:** proposed
- **Date:** 2026-09-21
- **Re-Review-Date:** 2026-12-21
- **Incident Reference:** campaign `campaign-dag-scheduler` sub-iterate R1
  (`iterate-2026-09-21-r1-depends-on-schema`),
  `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md`
  § "R1 — `depends_on` schema, `campaign_graph.py`, campaign-design
  conversation, resume-safe readiness"; external code review (Step 3.7)
  finding: case-fold inconsistency between `validate_dependency_graph`
  (case-insensitive by design) and `is_unit_ready`/`describe_blocker`/cycle
  detection/`check_frozen_contracts` (originally exact-case) was a real,
  high-severity deadlock bug.

## Context

`campaign_graph.py` was written new in this same sub-iterate at 265 lines,
comfortably under the 300-line limit. The external code-review cascade
(both reviewer passes, independently) found that the case-fold rule
`validate_dependency_graph` already applied to duplicate-id detection and
dependency-existence resolution was NOT applied to: the cycle-detection
adjacency graph itself (a mixed-case cycle such as `R0 -> b`, `B -> r0`
escaped detection because `_find_cycle_members`'s `dep in adjacency` check
was exact-case), and `check_frozen_contracts`'s unit-id lookup (a
case-mismatched id between `campaign.md` and `loop_state.json` silently
skipped the frozen-contract check). A write-time-accepted, case-mismatched
`depends_on` edge would otherwise permanently deadlock its dependent once
combined with `loop_state.py::is_unit_ready`'s own (separately-fixed)
exact-case lookup — a genuine, user-visible bug, not a style nit. Fixing it
required: case-folding the adjacency graph's keys AND edges (with an
original-casing lookup table for display in messages), case-folding
`check_frozen_contracts`'s id match and its frozen-vs-current list
comparison, and a defensive guard against a missing/non-string `id` (a
related, lower-severity finding — a mixed `str`/non-`str` id set previously
reached a bare `sorted()`/`set()` and could raise `TypeError` before any
finding was returned). Together these pushed the file from 265 to 316 lines. A further, later
round of external code review added a schema-validation guard to
`_read_loop_state_units` (syntactically valid but schema-invalid
`loop_state.json` — a non-dict element, or `"units"` not even a list —
previously reached `check_frozen_contracts`'s `.get()` calls and crashed the
supposedly resume-safe status projection), pushing the file to 322. The
3f-bis doubt reviewer then found the identical non-str-crash class survives
one function below (`validate_dependency_graph`'s bad-charset `sorted()`
over `depends_on` values, not just `ids`) — a one-line `str()` coercion plus
its docstring correction pushed the file to 328. An external Tier-3 PR
review (blocking) on the live GitHub gate then found
`safe_project_campaign_status` ran `validate_dependency_graph` (structural)
BEFORE `check_frozen_contracts` (per-unit revert), so a non-pending unit's
edited `depends_on` that was ALSO structurally invalid (e.g. an unknown id)
bypassed the promised per-unit revert and degraded the whole campaign
projection instead — reordering the two existing calls plus a corrected
docstring pushed the file to 343. The SAME external Tier-3 pass also found
`_read_loop_state_units` filtered retained units down to dict elements only,
without checking that a dict unit's own `depends_on` field was itself a
list: `check_frozen_contracts` builds `list(u.get("depends_on") or [])`, so
a hand-edited `loop_state.json` unit such as `{"id": "A", "status":
"in_progress", "depends_on": 5}` passed the dict filter and then raised
`TypeError` on that `list(5)` call, breaking the promised resume-safe
projection on syntactically-valid-but-schema-invalid input — a new
`_has_valid_depends_on` guard drops any retained unit whose `depends_on` is
present but not a list, pushing the file to 354.

## Ousterhout Argument

`campaign_graph.py`'s public interface (`id_charset_ok`,
`validate_dependency_graph`, `check_frozen_contracts`,
`safe_project_campaign_status`) is unchanged by this fix — no new function,
no new parameter, no new caller-visible shape. The growth is entirely
internal hardening of the SAME functions' existing bodies (case-fold
consistency + a defensive type guard), which is exactly what a deep module
absorbs: callers see nothing new, the module's internal correctness simply
improved. Splitting the case-fold helper (`lower_to_original`) or the
id-type guard into their own file would scatter three lines of shared state
across a module boundary for a helper with a single caller inside this same
file — a worse shape, not a better one.

## YAGNI Check

Every added line here fixes a finding an independent external reviewer
(twice, converging) demonstrated was reachable with real input (a
case-mismatched `depends_on` edge, which R1's OWN write-time validator
explicitly promises to accept). Nothing here is speculative: the fix exists
because leaving it unfixed ships a documented, write-time-legal input that
deadlocks a real campaign.

## Chesterton-Fence Check

There is no prior design decision pinning `campaign_graph.py` at exactly 300
lines — it is a brand-new file in this same sub-iterate, and the file being
under 300 lines at its first commit was incidental to the moment the code
review ran, not a boundary anyone deliberately drew. The repo-wide 300-line
convention is what's being exercised here, via its own stated exception
mechanism, not a file-specific commitment being broken.

## Decision

Grant an exception raising `campaign_graph.py`'s allowed `current` to 354.
Retirement plan: if a FUTURE change to this file (R4's `loop_claim.py`
sibling module aside) adds a fourth cross-cutting concern beyond
charset/structural validation, frozen-contract enforcement, and resume-safe
projection, that is the trigger to reconsider splitting cycle detection
(`_find_cycle_members`) into its own small graph-utilities module — re-review
at that point rather than waiting for the calendar date alone.

## Consequences

No downstream consumer's call signature changed at all — every fix is
internal to the existing four functions' bodies. The bloat-baseline
anti-ratchet now holds this file at 354 as its ceiling; a future PR that
grows it further without its own exception is correctly blocked.

## Rejected alternatives

- **Ship the case-fold fix only in `loop_state.py` (the readiness side) and
  leave `campaign_graph.py`'s cycle detection / frozen-contracts
  exact-case.** Rejected: this would still leave a validator that promises
  case-insensitive existence resolution but silently misses a mixed-case
  CYCLE (an actively dangerous graph a caller would believe was validated
  clean), and a frozen-contract check that silently no-ops on a
  case-mismatched id — both directly named by the external reviewers as
  live bugs, not just readiness-side.
- **Extract a tiny `_casefold_lookup` helper module shared by
  `campaign_graph.py` and `loop_state.py`.** Rejected for R1: the two
  call sites' case-fold logic is a single dict-comprehension line each, not
  a coherent shared abstraction yet — introducing a third module for two
  one-line call sites is the premature-abstraction failure mode this repo's
  own bloat checklist rejects. Revisit if R4's `loop_claim.py` needs the
  same pattern a third time.
