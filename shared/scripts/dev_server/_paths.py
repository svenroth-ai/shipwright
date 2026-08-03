"""The package's filesystem anchors — derived ONCE, with `os.path` only.

Internal to `dev_server`: none of the three names below is in `__all__`, so
this is not part of the package's public surface. It is imported by
`__init__.py` (which re-exports `_SCRIPTS_DIR` under the name the tests already
address) and by the three submodules that need one of its anchors — `state.py`
and `spawn.py` for `sys.path`, `profile_config.py` for `_PROFILES_DIR` alone.
It imports nothing from the package itself, so it is a leaf every other
submodule can import without a cycle.

**Why this module exists.** Before it, four places re-derived the same two
directories from their own `__file__`, three of them with `pathlib`, and three
of them independently inserted `shared/scripts` into `sys.path`. Duplicated
path arithmetic is not merely untidy here: a dirname-count slip in one copy
produces a *plausible but wrong* directory that is then inserted at
`sys.path[0]`, which is a live shadowing hazard rather than an import error
(documented in `test_scripts_dir_matches_the_pathlib_derivation_it_replaced` —
pointing the constant at a non-existent path leaves the rest of the suite
green).

**Why `os.path` and never `pathlib` in this file.** `pathlib` picks its
flavour from the process-global `os.name` *at construction*, while `os.path`
is bound to `ntpath`/`posixpath` when `os` is first imported and never
re-dispatches. The `dev_server` tests fake `os.name` (they must — the no-op
under test lives in `cmd_resolver`, which reads it), and under a fake a
pathlib path is a landmine whose detonation point is version-dependent: on
<=3.11 `Path.__new__` checks `_flavour.is_supported` and **construction**
raises; on >=3.12 construction slips past and the raise moves to the first
derivation (`.resolve()`, `.parent`, `/`). Both measured:
`NotImplementedError: cannot instantiate 'PosixPath' on your system`. CI pins
3.11. That is why this module exports **strings** and does its arithmetic with
`os.path` — callers needing a `Path` wrap at their own call site, where the
real `os.name` is in force.

This is the module-scope half of the lesson from
`iterate-2026-07-31-shared-tests-parallel-flake` (f0-race:shared/tests,
trg-f64d1c27), generalized from `__init__.py` to the whole package.
"""

from __future__ import annotations

import os
import sys

#: `shared/scripts` — the directory that must be on `sys.path` for the
#: package's `lib.*` imports (`lib.atomic_write` eagerly in `state.py`,
#: `lib.cmd_resolver` lazily via the `__init__.py` proxy) to resolve.
#: Pinned byte-for-byte against the `Path(__file__).resolve().parent.parent`
#: derivation it replaced by
#: `test_scripts_dir_matches_the_pathlib_derivation_it_replaced`.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

#: `shared/profiles` — sibling of `shared/scripts`, holding the stack-profile
#: JSON that `profile_config._profiles_dir` reads. Derived from the constant
#: above rather than from a second `__file__` walk, so the two cannot drift
#: apart and only one dirname count has to be right.
_PROFILES_DIR = os.path.join(os.path.dirname(_SCRIPTS_DIR), "profiles")


def _ensure_scripts_on_path() -> None:
    """Idempotently put :data:`_SCRIPTS_DIR` at the front of `sys.path`.

    The package's single `sys.path` mutation. Guarded, so repeated calls from
    the three sites that need it (`state.py` at import, the `__init__.py` lazy
    proxy, `spawn.py`'s fallback) insert at most one entry per process.

    Does no path arithmetic and touches no `pathlib`, so it is safe to call
    from a context where `os.name` has been faked — which the proxy's own
    tests do.
    """
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)
