# Architecture brief: spec chain (baseline-package P3)

Need: from an acceptance criterion, a person or an AI should find the runs that shaped it, each run's plan and its pull request, without guessing file names. Today the event carries neither plan path nor PR, 45 of 192 runs have no plan, and AC-level history exists for about 13% of ACs.

Options:
1. Add `plan_path` (and optional `pr`) to the run's recorded event; one plan-stub filename convention; a read-only lookup that joins event, catalog text and git to answer "which runs shaped AC X"; a warning-only F11 check for the stub.
2. Do nothing new: keep finding plans by fuzzy name matching and PRs by `git log --grep`.
3. Generate a tracked index file (AC to runs to plans to PRs) refreshed at each release.
4. Require the plan stub and the PR number as hard F11 errors.

Constraint: nothing may newly block a PR; an already-recorded event cannot be rewritten.
