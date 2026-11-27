# Architecture brief: route root-file joins through one function

## Problem
Shipwright will move ~20 root `shipwright_*` files into `.shipwright/config/`. During the transition every reader must look in the new place first and fall back to the old one. Today 98 call sites build the path themselves as `root / _sp.rel(key)` (a repo-relative string from the resolver), so a lookup added to the resolver would never reach them.

## Options
1. Keep the joins; make `rel()` itself return the new path once a repo is migrated (needs the project root, which `rel()` does not have, and turns every reader new-only).
2. Rewrite each join to `_sp.path(key, root)` (the resolver's existing join function) and forbid new joins with a guard; put the lookup inside `path()` in the next step.
3. Rewrite joins lazily, file by file, as the lookup step touches them.

## Constraints
No behaviour change in this step. Hooks run from a plugin cache that may be stale and must survive a missing resolver. Module-level constants are frozen at import time and cannot know the project root.
