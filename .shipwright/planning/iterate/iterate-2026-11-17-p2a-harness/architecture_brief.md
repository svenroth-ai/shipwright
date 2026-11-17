# Architecture Brief: a trace harness for the changelog release flow

## The problem
A skill that is a model reading prose cannot be proven unchanged when its mechanical steps move into code: no test records what a release leaves behind (commits, tags, remote refs, files, outward `gh` calls). Without that, a conversion bug looks the same as a changed behaviour.

## What already exists here
- `shared/testkit/minimal_valid_project.py`: builds a valid project one phase at a time.
- P1 seams: `SHIPWRIGHT_TEST_GH_ARGV_PREFIX` swaps the `gh` argv of the release scripts.
- `shared/testkit/event_log_probe.py` and per-test ad hoc git repos.

## What would newly, permanently exist
Three standard-library test-support files (scratch builder, `gh` stand-in, trace recorder with freeze check) and their tests. The trace files and lock they will later compare against are added by later units; tests keep the helpers correct.

## Options on the table
- **A:** One recorder module plus a scratch builder and a local `gh` stand-in that talks to a bare repository.
- **B:** Assert on individual outcomes per test (tag exists, file contains), no recorded trace.
- **C:** Do nothing; rely on the real-model runs at the operator stops.

## Constraints that are not negotiable
Standard library only for the testkit (ADR-044); no network, no API key may reach a scenario process; new files at most 300 lines.
