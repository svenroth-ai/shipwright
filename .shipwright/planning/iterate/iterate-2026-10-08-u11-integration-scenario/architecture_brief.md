# Architecture Brief: prove the five finalization gates work together without masking each other

## The problem
Five separate finalization checks each have their own unit tests, but nothing shows that they stay independent when
run over the same run: one failing check could hide a missing second check, and a change to one could silently
break another's inputs.

## What would newly, permanently exist
Nothing that runs in production: one test (plus a small helper) that builds a throw-away repo while the tests run.
Its maintainers are whoever changes one of the five checks.

## Options on the table
- **A:** one integration test that breaks one claim at a time over a freshly built repo and asserts every other gate stays green.
- **B:** commit a fixture repo with one case per gate.
- **C:** do nothing; rely on each gate's own unit tests.

## Constraints that are not negotiable
Untagged fixture tests cannot be committed (the test-tag gate refuses them); one pytest root per process.
