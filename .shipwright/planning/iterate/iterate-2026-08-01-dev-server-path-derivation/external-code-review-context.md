# Review context — iterate-2026-08-01-dev-server-path-derivation

A `small` iterate has no iterate spec by the phase matrix, so this file is the
spec context handed to the external code-review cascade. The cascade fired on
its own trigger (diff 317 lines > 100), not on complexity.

## What was asked

Triage card `trg-36f182f3` (dismissed as superseded; content unchanged,
re-verified at code on 2026-08-01):

> `dev_server` derives its `shared/scripts` constant three ways and inserts it
> into `sys.path` twice. `__init__.py:56` derives `shared/scripts` with
> `os.path` (hardened so a faked `os.name` cannot break it) and inserts it at
> `:86`, while `state.py:20` derives the same value with
> `Path(__file__).resolve().parents[1]` and inserts it FIRST — so the proxy's
> own guard can never fire in a normally imported process. `profile_config.py:98`
> and `spawn.py:47` carry two more pathlib derivations of nearby paths. All
> three are latent-safe today: two run at module scope where `os.name` is real,
> and `spawn.py`'s is a fallback reachable only when the package attribute is
> absent.
>
> **END STATE: one derivation, one insert, one constant for the package.**
>
> LANDMINE: this is ADR-045 territory — an eager `from lib.X` outside `lib/`
> resolves differently under the plugin-vs-shared root split and goes GREEN at
> F0, RED in CI. A lazy import only defers WHICH lib binds; it does not make it
> safe.

## Classification

- Path B CHANGE, **SIMPLIFY sub-mode**, **Spec Impact = NONE** (behavior-preserving)
- Complexity `small`; risk flags: none (verified diff-driven against
  `risk_detectors.py` — the changed paths match no IO_BOUNDARY /
  CROSS_COMPONENT / CI_SUPPLYCHAIN / TOUCHES_BUILD pattern)

## Acceptance criteria

1. Exactly ONE `__file__`-based path derivation remains in
   `shared/scripts/dev_server/`.
2. Exactly ONE `sys.path` insert remains in that package, and it is guarded.
3. `shared/profiles` is derived from the `shared/scripts` constant, not by a
   second independent `__file__` walk.
4. No observable behavior change (Spec Impact NONE).
5. No new eager `from lib.X` import outside `lib/`; no absolute import that
   could resolve differently under the plugin-vs-shared root split.

## Constraints a reviewer must honor

- **`_paths.py` uses `os.path` and never `pathlib`, deliberately.** `pathlib`
  picks its flavour from the process-global `os.name` *at construction*;
  `os.path` binds `ntpath`/`posixpath` when `os` is first imported and never
  re-dispatches. These tests fake `os.name`, and under a fake a pathlib path
  raises `NotImplementedError` (<=3.11 at construction, >=3.12 at first
  derivation). CI pins 3.11. "Modernize to pathlib" is the bug this code exists
  to prevent.
- **`state.py`'s eager `from lib.atomic_write import ...` was deliberately left
  eager and in place.** Making it lazy would only defer WHICH `lib` binds.
- **`shared/scripts/dev_server.py` (the shim) is deliberately NOT changed** — it
  bootstraps the package onto `sys.path`, so it cannot import from inside the
  package it is making importable, and it is outside "the package".

## Verification already performed

- 88 tests green (84 pre-existing + 4 new); ruff clean repo-wide.
- `behavior_snapshot verify` VERIFIED (behavior preserved).
- Node-id diff across the full 6-file population: 0 of the 84 baseline ids lost,
  exactly 4 added.
- Four mutation probes, each killed by exactly its intended test, including the
  package-attribute-absent spawn fallback.
- Final full `shared/tests` root: 7146 passed, 17 skipped, 20 deselected; final
  F0 suite: all 18 roots green.
- Internal cascade: spec-reviewer APPROVE, code-reviewer (1 medium + 4 low, all
  fixed), doubt-reviewer (1 medium + 1 low, both fixed).
