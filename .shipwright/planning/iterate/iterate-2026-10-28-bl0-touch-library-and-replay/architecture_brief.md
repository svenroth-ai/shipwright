# Architecture Brief: baseline touched-set library and replay (BL0)

## The problem

A pull request can change what an existing requirement (FR) means or how it is tested, and nothing compares what the diff touches with anything the operator approved. Before any gate is built, the operator needs measured numbers: how often a PR touches an existing FR, how often that would be a false alarm, and which kind of evidence (spec text, bound tests, executed code) notices what.

## What already exists here

- Keystone AC gate: derives per-AC text changes from the spec diff.
- Test-tag binding gate: tracks tests added, edited or moved, by body digest.
- Coverage is merged per tier for the diff-coverage gate; no per-test attribution.
- `work_completed` events carry `affected_frs` and (rarely) `fr_impact`.

## What would newly, permanently exist

A small library under `shared/scripts/tools/verifiers/` that derives a touched set from a git diff, plus one replay CLI and one committed report. Nothing runs in CI and nothing gates; the library is kept correct by its own unit tests and is the input to later, separate units.

## Options on the table

- **A:** Build the library and replay now, decide from measured data.
- **B:** Extend the existing keystone / test-tag gates with a touched-set report.
- **C:** Do nothing and design the gate from the brief alone.

## Constraints that are not negotiable

No change to ci.yml, verify_local.py, deliver_pr.py or any gate in this unit; new files at most 300 lines.
