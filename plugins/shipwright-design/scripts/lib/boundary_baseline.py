"""Session-start baseline for the design phase's write-boundary gate (FR-01.04 #11).

The logic is shared with the plan phase's gate (FR-01.03 #7) and lives in
``shared/scripts/lib/phase_boundary_baseline.py`` (full contract there). This module
binds it to the design phase's own file, ``.shipwright/design-boundary-baseline.json``,
and keeps the CLI the design SKILL runs first:
``python boundary_baseline.py --project-root <dir>``.

The shared module is loaded through ``shared_lib_loader`` into its private package,
never as ``lib.*``: this file is itself imported as ``lib.boundary_baseline`` by
``setup-design-session.py`` (this plugin's ``lib``), so a ``lib.`` lookup would hit
the wrong package (ADR-045).
"""

from __future__ import annotations

import json
import subprocess  # noqa: F401 - tests patch ``bb.subprocess.run`` (the same module object the shared code uses)
import sys
from pathlib import Path

_SHARED_SCRIPTS = str(Path(__file__).resolve().parents[4] / "shared" / "scripts")
_ADDED = _SHARED_SCRIPTS not in sys.path
if _ADDED:
    sys.path.append(_SHARED_SCRIPTS)
from shared_lib_loader import load_shared_lib  # noqa: E402

_pbb = load_shared_lib("phase_boundary_baseline", prefer_private=True)
if _ADDED:  # leave sys.path as found: shared/scripts holds a `tools` package
    sys.path.remove(_SHARED_SCRIPTS)

BASELINE_REL = _pbb.DESIGN_BASELINE_REL
_DELETED = _pbb.DELETED
dirty_paths = _pbb.dirty_paths
fingerprint = _pbb.fingerprint
at_repo_root = _pbb.at_repo_root
_head = _pbb.head


def _read(project_root: Path) -> dict | None:
    return _pbb.read_baseline(project_root, BASELINE_REL)


def write_baseline(project_root: Path) -> bool:
    """Record the design session's dirty set (see ``phase_boundary_baseline.write_baseline``)."""
    return _pbb.write_baseline(project_root, BASELINE_REL)


def session_changes(project_root: Path) -> list[str]:
    """The paths this design session changed (see ``phase_boundary_baseline.session_changes``)."""
    return _pbb.session_changes(project_root, BASELINE_REL)


def main() -> int:
    """``python boundary_baseline.py --project-root <dir>``: record the baseline
    (the design SKILL runs this before any other action)."""
    import argparse

    parser = argparse.ArgumentParser(description="Record the design boundary baseline")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    try:
        root = Path(args.project_root).resolve()
        state = ("written" if write_baseline(root) else "kept") if at_repo_root(root) else "not_written"
    except OSError:
        state = "not_written"
    print(json.dumps({"boundary_baseline": state}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
