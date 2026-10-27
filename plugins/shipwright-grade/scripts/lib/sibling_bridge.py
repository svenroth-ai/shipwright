"""sibling_bridge — locate a sibling plugin in the repo AND the installed plugin cache.

The grader reaches into ``shipwright-compliance`` (engine) and ``shipwright-adopt``
(detectors). ``<this plugin>.parent / "<name>"`` only names a sibling in the repo
layout; in the cache the parent is this plugin's own name directory. The shared
resolver ``shared/scripts/lib/sibling_plugin.py`` knows both layouts; it is loaded
by path (ADR-045: no ``lib`` import from a plugin script), under a unique module
name so it cannot shadow a sibling's own ``lib``.
"""

from __future__ import annotations

import functools
import importlib.util
import sys
from pathlib import Path


@functools.lru_cache(maxsize=1)
def _resolver():
    """The shared resolver module, loaded once per process; None if unavailable.

    The same loader block lives in ``shipwright-security`` finalize_security_compliance.py
    and ``shipwright-run`` orchestrator_pkg/constants.py — keep the three in step.
    """
    plugin = Path(__file__).resolve().parents[2]  # plugins/shipwright-grade | <cache>/…/<version>
    path = plugin.parent.parent / "shared" / "scripts" / "lib" / "sibling_plugin.py"
    try:
        spec = importlib.util.spec_from_file_location("_shipwright_sibling_plugin", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001 - a path probe must degrade to the repo guess, never raise
        sys.modules.pop("_shipwright_sibling_plugin", None)
        return None


def find_plugin(name: str, require: str | None = None) -> Path | None:
    """Root of the sibling plugin ``name`` (newest usable in the cache), else None."""
    here = Path(__file__).resolve()
    resolver = _resolver()
    found = resolver.find_sibling_plugin(here, name, require=require) if resolver else None
    if found is not None:
        return found
    legacy = here.parents[2].parent / name
    return legacy if legacy.is_dir() else None
