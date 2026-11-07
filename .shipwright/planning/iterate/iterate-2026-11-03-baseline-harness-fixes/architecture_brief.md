# Architecture Brief: baseline harness fixes and re-check command

## The problem
The operator-started e2e check suite for a built app reported many red items after a 6.5 hour run; most were wrong checks, not app defects. A fix could only be verified by another 6.5 hour run.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: the baseline checks, plus one npm script that runs them against a project folder that is already built.
