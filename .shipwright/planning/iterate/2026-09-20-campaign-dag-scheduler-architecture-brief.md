# Architecture Brief: dependency-aware campaign scheduling

## The problem

A Shipwright "campaign" (a set of related units of work toward one goal, each
its own git branch/PR) today always runs its units strictly one at a time,
even when two units have no relationship to each other. This is a measured
cost, not a theoretical one: the operator's most recent campaign ran for two
days elapsed, serially, with no attempt made to identify which of its units
could have proceeded independently. The operator's stated goal is to maximize
automation — running campaigns with as little manual babysitting as
possible — and cycle time is a standing concern for every campaign, not a
one-off complaint. At the start of a campaign, the operator wants to clarify
with the operating session what genuinely depends on what, then let
independent units proceed without waiting on each other while dependent ones
still wait for their prerequisite to land — with some units running hands-off
and others pausing for the operator's explicit go-ahead, so the operator is
asked only where it actually matters.

## What already exists here

- A per-campaign `branch_strategy` field controlling only which git ref each
  unit branches from (not scheduling order).
- A FIFO queue that hands out campaign units one at a time in list order, with
  no concept of readiness.
- A per-gate auto/approve/hard-stop policy mechanism, already used elsewhere
  in the project for a different kind of "mostly hands-off, pause where it
  matters" decision.
- A single shared working directory per campaign (not per unit), with a lock
  whose purpose is to prevent two units from being checked out into it at
  once.
- A per-unit review pass that runs against the currently checked-out branch
  before that unit's PR is allowed to merge.

## What would newly, permanently exist

A structured way to record which units depend on which, read by a scheduler
that decides what may start next; a policy field per unit controlling whether
it merges unattended or waits for the operator; and — depending on which
option below is chosen — a change to how many units may be checked out and
built at the same time, which touches the existing single-shared-directory
lock. Whoever changes campaign mechanics in the future has to keep this
scheduling logic and (if built) the multi-checkout model correct.

## Options on the table

- **A:** Record dependencies and the per-unit hands-off/pause policy as data
  only; the scheduler still runs one unit at a time but skips a unit whose
  recorded dependency hasn't finished yet, and asks the operator up front
  which units depend on which instead of leaving it to prose.
- **B:** All of A, plus letting genuinely independent units be checked out and
  built at the same time (not just scheduled without waiting), which requires
  moving from one shared working directory per campaign to one per active
  unit.
- **C:** Leave campaign mechanics unchanged; rely on the operator manually
  starting more than one independent session by hand when they already know
  two units don't depend on each other (already possible today).

## Constraints that are not negotiable

The project has no merge queue: even with independent units, only one unit's
PR may be merged at a time, re-verified against the current shared branch
immediately before merging.
