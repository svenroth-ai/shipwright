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

**Siblings resolve too.** The fallback loads into a private *package* whose
``__path__`` is ``shared/scripts/lib``, so a module that does
``from .sibling import …`` finds its sibling inside that same private namespace
and never touches ``lib``. It used to load each module as a lone top-level
sentinel, which meant a lib module with ANY intra-package import blew up here —
measured, once ``file_lock`` and ``atomic_write`` each grew one
(``ModuleNotFoundError: No module named 'file_lock_registry'`` /
``'durable_publish'``, trg-dc013d82). That failure was invisible to every test
root the change ran, and its callers swallow exceptions, so it would have
surfaced as silently lost triage findings rather than as a crash.

Note what is deliberately NOT done: ``shared/scripts/lib`` is never added to
``sys.path``. That directory contains ``config.py`` and ``state.py``, so putting
it on the global path would simply relocate the shadowing problem this module
exists to solve.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent  # shared/scripts
#: Namespace the fallback loads into. A package, not a flat prefix, so relative
#: imports between lib modules resolve within it.
_PRIVATE_PKG = "_shipwright_shared_lib"


def _private_package():
    """The private package standing in for ``lib``, created once."""
    pkg = sys.modules.get(_PRIVATE_PKG)
    if pkg is None:
        spec = importlib.machinery.ModuleSpec(_PRIVATE_PKG, None, is_package=True)
        pkg = importlib.util.module_from_spec(spec)
        pkg.__path__ = [str(_SCRIPTS_DIR / "lib")]
        sys.modules[_PRIVATE_PKG] = pkg
    return pkg


def _import(dotted: str):
    """The module's ONE dynamic import, so it needs only one suppression.

    Both resolution paths route through here. First-party hardcoded module
    identifiers only; no untrusted input ever reaches it. Dynamic resolution IS
    this module's purpose (ADR-045) — a static import is exactly what
    reintroduces the ``sys.modules['lib']`` collision it exists to survive.
    """
    # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
    return importlib.import_module(dotted)


def load_shared_lib(module_name: str):
    """Return ``shared/scripts/lib/<module_name>``, shadowing-proof."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        return _import(f"lib.{module_name}")
    except ImportError:
        pass

    _private_package()
    private_name = f"{_PRIVATE_PKG}.{module_name}"
    cached = sys.modules.get(private_name)
    if cached is not None:
        return cached
    if not (_SCRIPTS_DIR / "lib" / f"{module_name}.py").exists():
        raise ImportError(f"no shared lib module named {module_name!r}")
    # The private package's __path__ is what makes a sibling `from .x import y`
    # inside the loaded module resolve without touching `lib`.
    return _import(private_name)


__all__ = ["load_shared_lib"]
