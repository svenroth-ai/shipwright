# Architecture Brief: r1a-resolver-foundation

## The problem
Shipwright is moving its root `shipwright_*` files into `.shipwright/config/`. For the release that reads both places, three things must hold first: code that loads the path resolver under different import names must see the same object (otherwise per-layout state diverges), the root stub that old plugins keep seeing must be recognised identically everywhere, and nothing may confuse "file name" with "repo-relative path" once the two differ.

## What already exists here
- `shared/scripts/lib/shipwright_paths.py`: the single registry of root-file names, kinds and locks (shipped one week ago, no behaviour change, loaded under three import names).
- A guard test that forbids new literal root-file names outside the resolver.
- Hooks that fall back to literal names when the resolver import fails (stale plugin cache).

## What would newly, permanently exist
A small stdlib module that recognises (and renders) the plain-text root stub `SHIPWRIGHT-POINTER/1`; two resolver helpers that list a file's candidate locations; a load-time rule that collapses the resolver's import names onto one object; and tests (one of them a static scan) that keep hook fallbacks and basename comparisons honest. The campaign owner keeps them correct until R4 removes the legacy location.

## Options on the table
- **A:** Unify at load time inside the resolver; recogniser as its own module; helpers unused until R1c.
- **B:** One canonical import name everywhere, enforced by the guard; recogniser inside the resolver.
- **C:** Skip the foundation PR; build these pieces inside R1c where they are first used.

## Constraints that are not negotiable
Plugins have their own `lib` package (they cannot import `lib.*` from shared without shadowing it); the resolver must stay stdlib-only and load under any name; no production behaviour may change in this PR; the stub format is operator-signed (BRIEF 11.5 + 14).
