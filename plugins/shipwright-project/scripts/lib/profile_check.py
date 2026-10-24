"""Check a stack-profile NAME before it is written into a config (campaign stack-profile-resolver, S3).

``write_run_config.py --profile`` and ``checks/write-project-config.py --profile``
accept any name the resolver resolves (project > user > bundled) or a reserved
sentinel (``generic`` / ``detecting``); a name that fails the D3 rules or resolves
nowhere is rejected, so a typo is caught at write time and not by the first loader.

The resolver lives in ``shared/scripts`` (top-level module name, ADR-044/045): the
directory is APPENDED to ``sys.path`` for the import and removed again, because it
holds a ``tools`` package that would shadow this plugin's own.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# parents[0]=lib [1]=scripts [2]=shipwright-project [3]=plugins [4]=<repo root>.
_SHARED_SCRIPTS = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")


def check_profile(name: str, project_root: Path) -> None:
    """Resolve ``name``; returns ``None`` when it resolves (or is a sentinel).

    Raises ``ValueError`` (the resolver's error family) for a name that cannot be used, so the CALLER
    decides what that means (both writers print ``describe(...)`` and exit 4), and ``ImportError``
    when the shared resolver tree is missing (an install error).
    """
    if not os.path.isfile(os.path.join(_SHARED_SCRIPTS, "profile_resolver.py")):
        raise ImportError(  # an install problem (callers exit 1), not a bad name (exit 4)
            f"stack-profile resolver not found in {_SHARED_SCRIPTS}; the shipwright `shared/` tree is incomplete")
    added = _SHARED_SCRIPTS not in sys.path
    if added:
        sys.path.append(_SHARED_SCRIPTS)
    try:
        import profile_resolver
    finally:
        if added and _SHARED_SCRIPTS in sys.path:
            sys.path.remove(_SHARED_SCRIPTS)
    profile_resolver.resolve_profile(name, project_root)


def describe(name: str, exc: ValueError) -> str:
    """The one-paragraph reason printed for a profile name that cannot be used."""
    return f"profile {name!r} cannot be used ({getattr(exc, 'kind', 'error')}): {exc}"
