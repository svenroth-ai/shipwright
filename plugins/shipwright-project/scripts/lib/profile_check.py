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


def profile_error(name: str, project_root: Path) -> str | None:
    """``None`` when ``name`` resolves (or is a sentinel), else a one-paragraph reason.

    Raises ``ImportError`` when the shared resolver tree is missing (an install error).
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
    try:
        profile_resolver.resolve_profile(name, project_root)
    except ValueError as exc:  # branch on .kind only; the classes are not nameable here
        return f"profile {name!r} cannot be used ({getattr(exc, 'kind', 'error')}): {exc}"
    return None
