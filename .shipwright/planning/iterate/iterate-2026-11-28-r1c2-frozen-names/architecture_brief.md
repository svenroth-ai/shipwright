# Architecture brief: R1c-2

**Problem.** R1c-1 made `shipwright_paths.path(key, root)` find a moving root file in `.shipwright/config/` first, then at the root, and fail loudly on two copies. About 60 modules still build those paths from module constants frozen at import (`NAME = _sp.rel(key)`, joined as `root / NAME`), so after the R3 migration they would read only the root (or the pointer stub) and miss the real file.

**Options.**
1. Route every JOIN of a frozen moving name through `path()` now (codemod + hand fixes + a guard that forbids new ones); leave names used as git pathspecs / path sets / messages for a separate PR (R1c-3), because they need both-layout sets or per-commit names, not a lookup.
2. Flip `rel()` itself to the new location and fix fallout (rejected in BRIEF 12.1: every reader turns new-only, an unmigrated repo reads as "not a Shipwright project").
3. Do nothing until R3 and rewrite then (rejected: R3 is the migration itself; the readers must already work in both layouts before it, BRIEF 5).
4. Replace each constant with a lazy function per module (more surface, same effect as option 1 at the join site).

**Chosen.** Option 1, split from the set/pathspec work. Plus the two registry row flips the operator decided (D1 `dev_server` -> `.shipwright/runtime/`, D2 `audit_config` -> `.shipwright/config/`), whose readers already go through `path()`.

**Cost.** 69 files, mostly one-line mechanical rewrites; one new guard test; one end-to-end test. No behaviour change in any existing project (no new-place file exists yet).
