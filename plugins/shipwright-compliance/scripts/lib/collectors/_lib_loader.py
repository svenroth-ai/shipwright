"""Robust loader for the SHARED requirement/traceability lib modules (ADR-045).

The compliance plugin has its OWN top-level ``lib`` package (``scripts/lib``), and
several tests bind ``sys.modules['lib']`` to it at collection time
(e.g. ``test_enforcement_hooks.py`` does ``from lib.thresholds import …``). A plain
lazy ``from lib import fr_tag_grammar`` after a ``sys.path`` insert is then INERT — it
resolves against the already-bound compliance-local ``lib`` and raises ImportError for
shared-only modules. That is the order-fragile CI-red/local-green class ADR-045 warns
about, and it is NOT fixed by laziness alone.

``load_shared_lib`` saves + clears any pre-bound ``lib``/``lib.*`` from ``sys.modules``,
inserts ``shared/scripts`` on the path, imports the requested SHARED ``lib.<name>`` by
package name (so ``fr_tag_grammar``'s relative ``from .requirement_model`` still
resolves), then RESTORES the caller's prior ``lib`` binding — leaving no lasting
``sys.modules`` mutation that could clobber a caller's compliance-local ``lib``. The
returned shared module object is cached, so repeat calls skip the save/clear/restore.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[5] / "shared" / "scripts"
_CACHE: dict[str, object] = {}


def load_shared_lib(name: str):
    """Import + return the SHARED ``lib.<name>`` module, robust to a pre-bound ``lib``."""
    cached = _CACHE.get(name)
    if cached is not None:
        return cached

    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for key in saved:
        sys.modules.pop(key, None)
    if str(_SHARED_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SHARED_SCRIPTS))
    try:
        module = importlib.import_module(f"lib.{name}")
        _CACHE[name] = module
        return module
    finally:
        for key in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            sys.modules.pop(key, None)
        sys.modules.update(saved)


__all__ = ["load_shared_lib"]
