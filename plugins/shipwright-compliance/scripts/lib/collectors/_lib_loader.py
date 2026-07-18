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
    # PRECEDENCE, not mere presence. ``lib`` is a REGULAR package (every plugin's
    # scripts/lib has an __init__.py), so ``import lib.X`` binds to exactly the FIRST
    # ``lib`` on sys.path — merely checking "shared/scripts is somewhere on the path" is
    # not enough. Once another plugin's scripts dir sits ahead of it, ``lib`` resolves to
    # THAT plugin and every shared-only module raises ModuleNotFoundError. It stayed
    # latent because the early call sites cached their module while the ordering still
    # happened to favour shared; a call made later in the same session did not.
    saved_path = list(sys.path)
    shared = str(_SHARED_SCRIPTS)
    sys.path.insert(0, shared)
    try:
        # `name` is always a hardcoded module identifier from first-party callers. The
        # ACTUAL fixed set for THIS loader is three: requirement_model, fr_tag_grammar,
        # fr_fold_map (the collector package). The audit groups' drift_parsers /
        # bloat_baseline / events_log / … go through the unrelated
        # `audit_adapters.load_shared_lib`, which loads by file location under a sentinel
        # name and never had the `lib`-precedence problem. Keep them there: this loader
        # RESTORES sys.path on exit, so a module that mutates sys.path at import time
        # (bloat_baseline does) would silently lose that insertion here.
        # No untrusted input reaches it, and the f-string is
        # confined to the first-party ``lib.*`` namespace. import_module by package
        # name (not spec_from_file_location) is required so shared modules' relative
        # imports (e.g. fr_tag_grammar's ``from .requirement_model``) resolve.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        module = importlib.import_module(f"lib.{name}")
        _CACHE[name] = module
        return module
    finally:
        # Restore the caller's exact path, then re-add shared/scripts at the END if it
        # was not already there — preserving the historical "it is now importable" side
        # effect while guaranteeing it can never SHADOW a plugin's own ``lib`` for a
        # later bare ``from lib.X import …``. Front-precedence is scoped to the import.
        sys.path[:] = saved_path
        if shared not in sys.path:
            sys.path.append(shared)
        for key in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            sys.modules.pop(key, None)
        sys.modules.update(saved)


__all__ = ["load_shared_lib"]
