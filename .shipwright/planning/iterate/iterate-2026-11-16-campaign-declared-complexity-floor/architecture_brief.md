# Architecture Brief: campaign-declared-complexity-floor

Campaign context: this is a bug unit found while running the campaign profile-architecture-rules (units U1, U2, U4, U5, U6). It changes the framework machinery that sizes a campaign unit; it is not part of that campaign's own product scope.

## The problem
An operator declares each campaign unit `medium` in the brief. The unit runner then sizes the unit again from its spec text and its diff and lands on `small` for ordinary 100-200 line changes, so the plan review, architecture review and doubt review are recorded not-applicable. They ran only because the orchestrator asked.

## What would newly, permanently exist
One explicit line in each campaign unit's spec (`Complexity: <level>`) that two existing classification steps read as a floor, plus one field in an existing per-run record that an existing finalization check compares. No new gate, workflow or storage.

## Options on the table
- **A:** the unit spec carries the declared level; both classification steps and the finalization check use it as a floor.
- **B:** the orchestrator passes the level to the runner as a command-line override.
- **C:** change the size rules so ordinary 100-200 line changes classify as medium.
- **D:** do nothing; the orchestrator keeps telling runners to record medium.

## Constraints that are not negotiable
The campaign-mode reference file is at its size cap and may not grow.
