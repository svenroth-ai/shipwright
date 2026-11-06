Goal: Run the shared tier and the plugins/integration/replay tier as two parallel CI jobs; keep Python (lint + test) as the one required check that gathers and gates
Reason: CI wall-clock: the single serial job takes ~16 min on push and ~20 min on a PR
Reference: CI-duration iterate 2/3 (spec .shipwright/planning/iterate/2026-11-06-ci-parallel-jobs.md)
