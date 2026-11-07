# Architecture Brief: proving the per-run event drop layout before it is switched on

## The problem
The repo is about to move its shared event log from one file to one file per run. Before the switch, the team needs evidence that the whole system works together, is fast enough at 300 files, and can be rolled back without losing history.

## What already exists here
- Per-unit tests for writers, readers, fold, integrity and mixed-version checks; a bare-origin harness and a standing replay gate.
- Two rollback tools (emergency fold, full fold) with unit tests on small fixtures.

## What would newly, permanently exist
Three test files (whole-system scenarios, a 300-file microbenchmark, a rollback rehearsal on a copy of the real log) and a flip-readiness note; plus small fixes the rehearsals force (a staging call that fails with 1000 files on Windows, a CI check that blames a PR for events it wrote before the switch).

## Options on the table
- **A:** whole-system tests + benchmark + rehearsal on a copy of real history, fixing what they hit.
- **B:** rely on the per-unit tests and flip.
- **C:** a one-off manual rehearsal script, not kept as tests.

## Constraints that are not negotiable
The real event log is never modified; no CI workflow is changed; the flip itself stays an operator decision.
