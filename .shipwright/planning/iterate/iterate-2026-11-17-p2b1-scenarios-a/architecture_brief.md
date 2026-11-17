# Architecture Brief: replay driver and first scenarios for the changelog pilot

## The problem
The deterministic-first pilot will move mechanical steps of `/shipwright-changelog` out of prose into code. Today's
behaviour exists only as prose a model reads, so there is nothing to prove the conversion keeps it. The pilot needs a
recorded, repeatable account of what the unchanged prose does, scenario by scenario, before any step moves.

## What already exists here
- A harness (scratch project, `gh` stub, trace recorder, driver interface, freeze check) delivered by the previous unit.
- Unit tests that grep SKILL.md text, and a few that run its fenced blocks against stubs.
- The skill's own scripts, each with its own tests.

## What would newly, permanently exist
Test-support code and generated trace files in the changelog test root: a replay driver that runs the commands of the
prose one step at a time, an oracle restating FR-01.09's acceptance criteria, scenarios, and about 20 committed trace
files. The conversion units and the operator keep them correct (the freeze test pins them after the operator's stop 2).

## Options on the table
- **A:** a replay driver plus scenarios and committed traces, as above.
- **B:** only unit tests per script, no end-to-end record of the prose.
- **C:** run the real model against the skill for each scenario and record it.
- **D:** do nothing.

## Constraints that are not negotiable
The pilot brief requires the replay driver and traces (programme P7); the skill and its scripts stay unchanged in this unit.
