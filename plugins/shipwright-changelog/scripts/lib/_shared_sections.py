#!/usr/bin/env python3
"""Reach the shared Keep-a-Changelog section predicates without binding ``lib``.

``changelog_sections`` lives at ``shared/scripts/`` top level (ADR-045) so this
plugin's writer and the release-time ``aggregate_changelog.py`` share exactly
one implementation of "where does a section start, where does it end, where does
a new one go".

Reaching it by putting ``shared/scripts`` on ``sys.path`` would work today, but
that directory ALSO contains a ``lib/`` package. Placing it ahead of this
plugin's own ``scripts/lib`` on the path is the collision ADR-045 exists to
prevent, and it is bidirectional: whichever ``lib`` is bound first wins, and the
other side's siblings vanish — a failure that surfaces far from its cause
(``conventions.md:43``). Loading the file directly under a private module name
binds no package at all, so neither direction can shadow the other.

Safe here because ``changelog_sections`` imports nothing but ``re``. A module
with intra-package imports must NOT be loaded this way — its siblings would
still resolve against whatever ``lib`` happens to be bound.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PRIVATE_NAME = "_shipwright_shared_changelog_sections"


def _shared_module_path() -> Path:
    """Locate ``shared/scripts/changelog_sections.py``.

    ``parents[4]`` resolves in both layouts this plugin runs from:

    * the repo — ``plugins/<name>/scripts/lib/`` → repo root
    * the marketplace cache — ``cache/shipwright/<name>/<version>/scripts/lib/``
      → ``cache/shipwright``, where the ``ensure_shared_cache`` SessionStart
      hook mirrors ``shared/``

    The two happen to sit at the same depth because the cache substitutes a
    version directory for the repo's ``plugins/``. This is the same hop that
    the ``shipwright-compliance`` plugin's ``test_evidence`` module already
    relies on, in production.
    """
    return (
        Path(__file__).resolve().parents[4]
        / "shared" / "scripts" / "changelog_sections.py"
    )


def load_changelog_sections():
    """Return the shared predicates module, loading it once per process."""
    cached = sys.modules.get(_PRIVATE_NAME)
    if cached is not None:
        return cached

    path = _shared_module_path()
    # Check the FILE, not the spec: `spec_from_file_location` picks a loader by
    # suffix and deliberately does not stat the path, so for a `.py` location it
    # always returns a spec with a SourceFileLoader. Testing `spec is None`
    # would leave this arm dead and hand the operator a bare FileNotFoundError
    # from exec_module instead of an actionable message — and the
    # ensure_shared_cache hook is fail-open, so a missing shared/ really does
    # reach here.
    if not path.is_file():
        raise ImportError(
            f"cannot load the shared changelog section predicates from {path}: "
            "shared/ is missing from this install. The ensure_shared_cache "
            "SessionStart hook mirrors it from the marketplace clone; in a dev "
            "checkout, run scripts/update-marketplace.sh."
        )
    spec = importlib.util.spec_from_file_location(_PRIVATE_NAME, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"no Python loader for {path}")

    module = importlib.util.module_from_spec(spec)
    # Register BEFORE exec_module: a module that resolves its own name while
    # executing (a dataclass, a decorator) fails on a loader that registers
    # afterwards. Unregister again if execution fails, or the fast path above
    # would hand out a half-initialised module for the rest of the process.
    sys.modules[_PRIVATE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_PRIVATE_NAME, None)
        raise
    return module


__all__ = ["load_changelog_sections"]
