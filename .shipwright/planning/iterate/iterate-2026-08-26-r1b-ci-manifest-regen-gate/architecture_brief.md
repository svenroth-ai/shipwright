# Architecture Brief: ci-manifest-regen-gate

## The problem

The compliance system produces a document (`test-traceability.json`) that
claims which requirement is proven by which test. That document is written by
whoever runs a regeneration command locally, and nothing checks it against a
real, complete test execution before it is committed. A regeneration run with
a partial or stale test pass — or none at all — still produces a
plausible-looking document, and it is trusted as evidence anyway. There is
currently no point in the pipeline where this document's claims are checked
against an actual, independent test run.

## What already exists here

- A local test runner (`run_test_suite.py`) that already executes every test
  area of the project on each change, before it is committed.
- A tool (`evidence_drop.py` / `run_full_suite_evidence.py`) that can stage
  raw test-run reports for the compliance system to read.
- A generator (`test_links.py`) that turns staged test-run reports into the
  traceability document.
- No automated step anywhere checks that document against a fresh,
  independent test run.

## What would newly, permanently exist

An automated check, run by the CI system on every pull request, that
re-executes the tests, regenerates the traceability document from that real
run, and compares it to the one committed in the PR — reporting a mismatch,
not yet blocking on one. Whoever maintains the CI pipeline is responsible for
this check staying correct as the traceability document's shape evolves.

## Options on the table

- **A:** Build the automated CI check now, reporting mismatches visibly but
  not blocking merges yet.
- **B:** Build the automated CI check now, blocking merges on any mismatch
  immediately.
- **C:** Do nothing — leave the traceability document self-reported, with no
  independent check.

## Constraints that are not negotiable

none
