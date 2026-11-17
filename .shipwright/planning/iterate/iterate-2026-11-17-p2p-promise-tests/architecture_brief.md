# Architecture Brief: promise tests and the promise lock's hashing for the changelog skill

## The problem
The deterministic-first pilot will move mechanical steps of `/shipwright-changelog` from prose into a command-line
tool. A recorded account of what the prose does today (the traces) proves the move changed nothing, but it also locks
accidents. What the skill promises its users (the fifteen acceptance criteria of FR-01.09) needs its own tests, which
must keep passing, unchanged, after the move, and a way to detect that such a test was weakened rather than merely
reformatted.

## What already exists here
- A replay driver that runs today's prose one step at a time, an oracle that re-states each criterion, 25 scenarios
  with committed traces, and a freeze test that will pin them at the operator's next stop.
- Existing tests tagged with the criteria, several of which exercise code the skill never calls.
- A table in the spec that records where a criterion moved when its requirement is split.

## What would newly, permanently exist
Twenty promise tests (one or two per criterion), a promise list in the shape the skill-check tool uses, a file of
eight judgement scenarios in that tool's schema, a small standard-library hashing helper with its tests, and a
meta-test over the list. The operator's stop 2 locks the hashes; later units keep the tests green.

## Options on the table
- **A:** dedicated promise tests through the driver, the list, the scenarios file and the hashing helper, as above.
- **B:** tag the existing scenario tests as the promises and hash those.
- **C:** hash the existing tests tagged with the criteria and add nothing.
- **D:** do nothing; lock only the traces.

## Constraints that are not negotiable
The skill and its scripts stay unchanged; the tests must be green against the unchanged skill; the hash must ignore
formatting and comments and notice a changed assertion in a test, a helper or a fixture; the criteria stay unchanged.
