# Architecture brief: ci-parallel-jobs

**Question:** should this be built at all, and in this shape?

**Problem.** `ci.yml` is one serial job `Python (lint + test)` (~16 min push, ~20 min PR). The four heavy test steps
account for ~15 of those minutes (plugins 3, shared 8, integration 2.3, events replay 1.8).

**Chosen option.** Four parallel test jobs, each internally serial and one pytest root per process. Results travel
by artifact (JUnit + coverage data) to the original job, which keeps its name (the only required check) and ALL
its gate steps, and fails closed on `needs` results. Expected ~10-11 min push, ~14-15 min PR.

**Permanent additions.** 4 jobs; a `needs`-result step; a coverage-set gate; artifact upload/download conventions;
advisory-check declarations in `shipwright_run_config.json`; setup repeated per job.

**Options considered and rejected.**
- Move only `shared/tests` out (same moving parts, lower ceiling; blocks the later sharding gain).
- xdist inside one job (~4 min): conflicts with the standing decision that CI stays serial as the independent check
  against the parallel local run.
- Do nothing: 5-6 min saved per run across automerge and campaign PRs is real.
