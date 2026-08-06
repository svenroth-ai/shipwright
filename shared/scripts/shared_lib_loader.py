"""Importing ``shared/scripts/lib/*`` from a module that lives outside ``lib/``.

ADR-045 keeps cross-plugin helpers (``triage.py``, ``known_failures.py``, …) at
``shared/scripts/`` top level, because every plugin carries its own
``scripts/lib`` package and an eager ``from lib.X import …`` would bind
``sys.modules['lib']`` to whichever one got there first.

Importing them **lazily** was the accepted mitigation, and it is not enough: if
a plugin's test session has ALREADY imported its own ``lib.*``, the lazy import
still resolves against that package and raises ``ModuleNotFoundError`` on a
sibling that only exists under ``shared``. Latent for a long time because every
triage producer emitted from a subprocess; surfaced by the first in-process one
(iterate-2026-07-27-test-phase-record-honesty).

:func:`load_shared_lib` tries the normal package import first — unchanged in the
common case — and falls back to loading the file directly under a private module
name that touches no ``lib`` namespace at all.

**A module reached through here must not rely on a bare intra-package import.**
``from lib.sibling import …`` would resolve that sibling against the *shadowing*
package, and the plain relative ``from .sibling import …`` cannot resolve at all
under the path fallback, which has no package context.

The rule is therefore "spell it both ways", not "have no siblings": a module may
depend on a sibling if it tries the relative import first and falls back to the
sibling's unique top-level name, putting ``shared/scripts/lib`` on ``sys.path``
itself (this loader adds ``shared/scripts``, not ``lib``). Two modules do exactly
that and are pinned in both modes by ``shared/tests/test_jsonl_records_load_modes.py``
— ``lib/jsonl_records.py`` (needs ``atomic_write``) and ``lib/triage_integrity.py``
(needs ``jsonl_records`` + ``triage_delivery``), both since
iterate-2026-08-06-p2-19c-corruption-absence. Note the consequence recorded in the
latter: under the fallback a sibling is bound under its top-level name, a DISTINCT
module object from any sentinel-named copy, so classes from the two do not compare
equal — duck-type across that boundary, never ``isinstance``.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent  # shared/scripts


def load_shared_lib(module_name: str):
    """Return ``shared/scripts/lib/<module_name>``, shadowing-proof."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        # First-party hardcoded module identifiers only; no untrusted input.
        # Dynamic resolution IS this module's purpose (ADR-045) — a static
        # import is what reintroduces the `sys.modules['lib']` collision.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        return importlib.import_module(f"lib.{module_name}")
    except ImportError:
        pass

    private_name = f"_shipwright_shared_lib_{module_name}"
    cached = sys.modules.get(private_name)
    if cached is not None:
        return cached

    path = _SCRIPTS_DIR / "lib" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(private_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load shared lib module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[private_name] = module
    spec.loader.exec_module(module)
    return module


__all__ = ["load_shared_lib"]
