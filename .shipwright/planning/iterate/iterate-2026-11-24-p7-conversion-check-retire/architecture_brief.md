# Architecture Brief: end check for a converted plugin

## The problem
After the changelog conversion nothing proves it is complete: that the moved mechanics are gone from the prose, that the checks which replaced them exist, that a promise marked passing really ran, and that the test which guards the freeze was not deselected. The current meta test proves only that a named test exists.

## What would newly, permanently exist
- One operator-run checker script with a registry file (per converted plugin: forbidden prose patterns, required code patterns, seeded tests, a sentinel test), and a small JUnit reader.
- A JSON export of the promise list for the skill-check tool.
- Deleted: the inventory checker, its data files, and the two inventory-bound coverage checks.

## Options
1. Registry-driven checker plus JUnit reader, run by an operator (the proposed change).
2. The same, wired as a CI gate step.
3. A session-outcome hook inside the frozen golden conftest.
4. Do nothing: keep the existence-only meta test and rely on review.
