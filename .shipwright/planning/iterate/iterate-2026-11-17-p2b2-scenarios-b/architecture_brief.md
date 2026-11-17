# Architecture Brief: the second half of the changelog scenarios, the coverage checks and the seeded regressions

## The problem
The deterministic-first pilot will move mechanical steps of `/shipwright-changelog` out of prose into code. The first
half of the scenarios records what today's prose does for nine situations. Release delivery, manifests, the release
page, a dispatched run, the refusal paths and the phase-complete block are still unrecorded, and nothing yet checks
that the scenarios cover the prose and the acceptance criteria, or that they would notice a real regression.

## What already exists here
- The harness, the replay driver, the oracle and nine scenarios with committed traces from the previous units.
- An inventory of the skill's sections, with a class per section, and the FR-01.09 acceptance criteria in the spec.
- The skill's own scripts, each with its own tests.

## What would newly, permanently exist
About 25 more scenarios with committed trace files, one more replay step, an oracle function per acceptance criterion,
three small coverage functions that read the inventory, the prose and the spec, and a test that seeds three regressions.
The conversion units and the operator keep them correct (the freeze test pins them after the operator's stop 2).

## Options on the table
- **A:** the scenarios, the checks and the seeded regressions, as above.
- **B:** only the scenarios; coverage and regression catching judged by hand at the end of the pilot.
- **C:** record each situation by running the real model against the skill.
- **D:** do nothing.

## Constraints that are not negotiable
The pilot brief requires the scenarios, the coverage checks and the three seeded regressions before any step moves
(programme P7, P8); the skill and its scripts stay unchanged in this unit.
