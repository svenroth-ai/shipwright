# Architecture brief: new-then-old lookup for Shipwright's project files

## Problem
Shipwright is moving ~20 tool-owned root files (`shipwright_*_config.json`, baselines, registers) into `.shipwright/config/`. Old and new plugin versions will coexist for a while (other machines, stale plugin caches, CI). Before any repository is migrated, every reader must find a file in either place, and a file that exists in both places (or a half-finished move) must never be read silently. The one root file old plugins use as a project marker (`shipwright_run_config.json`) will be replaced by a small plain-text pointer stub at the move. Two files (`run_config`, `ac_registry`) are written under an advisory lock that sits next to the data file today; old writers will keep taking that lock.

## Options
1. Put the lookup inside the resolver's existing `path(key, root)` (every reader already goes through it since the previous step): new place if it exists, else the root; both copies = error unless byte-identical; stub without its migrated copy = error. Writers use the same answer. Writers of the two locked files take two locks in a fixed order (old root lock, then one under `.shipwright/locks/`).
2. Separate read and write functions: `read_path()` with the lookup, `write_path()` always returning the root until the flip release; one lock as today, moved at the flip.
3. Do nothing until the flip release, then flip all readers and writers at once (no dual read).

## Constraints
No current repository has a `.shipwright/config/` copy, so nothing may change for them. Hooks run from a plugin cache that can be older or newer than the shared library next to it. The resolver must stay stdlib-only and load under several module names. Files stay at or under 300 lines.

## Permanent additions
One stdlib module (the lookup and its error type); one lock directory entry per locked file (`.shipwright/locks/`, already the lock home and git-ignored). The legacy lock and the root fallback are removed at R4.
