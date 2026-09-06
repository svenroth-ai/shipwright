# Architecture Brief: fr-hygiene-touched-rows

## The problem

An adopted downstream project's requirement catalogue (`.shipwright/planning/*/spec.md`)
can accumulate FR rows and acceptance criteria that violate the project's own
authoring rules — implementation detail in names/descriptions, criteria not in
Given/when/then shape, or an unresolved "TBD" acceptance-criteria placeholder —
while every compliance check reports clean, because the checks that would catch
this are advisory-only (a deliberate choice, so a repo's pre-existing content can
clean up gradually without reddening CI). The gap: nothing stops a CURRENTLY
authored row — one this run itself just wrote or edited — from carrying the same
violations, and no signal exists anywhere for how long a TBD placeholder has sat
unresolved.

## What already exists here

- Group I (`plugins/shipwright-compliance/scripts/audit/group_i*.py`): I1
  (name), I2 (description), I6 (no criteria) — advisory, whole-catalogue,
  no distinction between legacy and freshly-authored rows.
- `check_integration_coverage` / `check_ci_supplychain_ack`
  (`shared/scripts/tools/verifiers/`): the existing precedent for a
  diff-scoped, non-dodgeable F11 gate that recomputes from the branch diff
  rather than trusting a self-reported flag.

## What would newly, permanently exist

A new F11 verifier (`check_fr_hygiene_on_touched_rows`) that diffs a touched
`spec.md` against the branch's merge-base and blocks finalization if any FR row
this run added or edited violates the authoring rules — running at every
complexity, with no opt-out. A companion advisory check (I8, in the existing
Group I dashboard) reports how many days a TBD placeholder has survived,
computed by reading git history (`git blame`) rather than storing new state.
From now on, every iterate that touches a spec.md is held to the letter of the
authoring rules for the rows it wrote, and the framework's own F11 verifier
registry gains one more entry that must keep working as the git-history-reading
primitives it depends on evolve.

## Options on the table

- **A:** Add a new, diff-scoped, non-dodgeable F11 gate that blocks
  finalization on a dirty row this run touched, plus an advisory TBD-age
  signal (the shape actually built).
- **B:** Promote I1/I2/I6 globally from advisory to blocking for the whole
  catalogue, immediately.
- **C:** Leave Group I advisory-only; rely on periodic manual/detective audits
  (e.g. `/shipwright-compliance`) to surface dirty rows after the fact, with no
  new blocking mechanism.

## Constraints that are not negotiable

The operator has already decided, for this run: the new gate hard-blocks
finalization immediately (no advisory warm-up period); the TBD-aging threshold
is 90 calendar days; the criterion-shape check (I7) ships in this same run.
These are the run's own binding scope decisions, not external platform/
regulatory limits — noted here for context, not as something outside this
review's remit to question.
