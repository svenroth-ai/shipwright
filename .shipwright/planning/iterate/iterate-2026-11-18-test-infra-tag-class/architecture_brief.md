# Architecture Brief: test-infra-tag-class

## The problem

The finishing gate for a change refuses an added or edited test that does not name the requirement it proves. Tests of the
test harness itself (golden-trace driver, gh stub, hash helper, their meta-tests) prove no product requirement. Today their
authors attach an unrelated requirement tag just to get past the gate, so the requirement-coverage numbers claim proof that
does not exist, and nothing in the data says which tests are stand-ins. This happened across roughly nine tests in one
campaign and will recur for every harness. The operator does not want a loophole through which real requirement tests can
skip their tag.

## What already exists here

- The gate itself: a per-test tag check with ratchet semantics (only added or edited tests are judged).
- Two per-test exemptions recorded in the finishing entry: one for functions the test runner does not collect, one for pure renames.
- A per-change label (`docs`, `tooling`, `compliance`, `infra`) that lets a whole change skip naming a requirement, checked against the diff's paths.
- A traceability collector that lists tests as tagged or untagged and computes requirement coverage from tagged ones.
- A project-aware path catalog for the per-change labels.

## What would newly, permanently exist

A third per-test class: a test declares in its own source that it is infrastructure and proves no requirement, and the gate
accepts that declaration only under conditions it checks itself. It would add one marker, one small path list that must be
kept current as harnesses appear, and one more case in the gate's verdict. The gate's owners keep it correct from now on.

## Options on the table

- **A:** A new per-test exemption code in the finishing entry, same shape as the existing two.
- **B:** A source-declared marker on the test, accepted by the gate only for tests at paths listed in a catalog.
- **C:** Reuse the per-change label: a change labelled tooling/infra relaxes the tag rule for all its tests.
- **D:** Give the harness its own real requirement and tag its tests to it.
- **E:** Do nothing; keep stand-in tags and record them in the findings file.

## Constraints that are not negotiable

- Must not reduce what the gate catches for ordinary requirement tests.
- Must work for pytest tests; TS/JS tests may stay as they are.
