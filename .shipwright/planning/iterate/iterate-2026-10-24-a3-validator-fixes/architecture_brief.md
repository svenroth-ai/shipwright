# Architecture Brief: phase validator correctness fixes

## The problem
The between-phase validators judge the wrong things: design looks for mockups where the design phase never writes them and fails runs that have no UI, plan checks the wrong split, a skip reason under one of two accepted keys is rejected, and a canon check that could not run (or ran without a run id) reports as a clean pass.

## What would newly, permanently exist
Nothing. This changes machinery that already exists: the phase validators' checks and the canon bridge's reporting (plus one sibling module holding the two split-aware validators).
