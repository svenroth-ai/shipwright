# Architecture brief: where do the root `shipwright_*` file names live?

## Problem
About 350 non-test source files (Python, bash, YAML, markdown prompts, JSON profiles) each hard-code the names of ~20 root files (configs, baselines, a register, a derived results file). A later campaign step wants to move these files into `.shipwright/config/` (without breaking old plugins or git-history readers). This step must prepare that move WITHOUT moving anything or changing any behaviour.

## Options
1. Do nothing now; do the move later by a repo-wide search-and-replace of the literals.
2. One stdlib-only module that owns the names (a registry with a kind per file, path/lock/per-commit helpers), every Python reference migrated to call it, plus a guard test that forbids new literals (non-Python carriers held to a no-growth ratchet).
3. Same module, but only for the handful of "core" readers; leave the long tail of literals alone.
4. A config/data file (JSON) listing the names, read at runtime by every consumer.

## Constraints
Plugins each have their own `lib` package, so a shared module needs a unique import name. Many files sit exactly at a size baseline that may not grow. Old plugin versions and hooks run from a cache during a skew window.
