#!/usr/bin/env python3
"""SessionStart hook: scan project root for stale legacy artifact dirs.

Wired in every plugin's ``hooks/hooks.json`` as the third SessionStart
hook (after ``capture_session_id.py`` and ``phase_session_start.py``).

Behavior per ``ARTIFACT_MIGRATIONS`` entry:
- ``status="in_progress"`` → warn-only stderr notice + drift report
  written to ``.shipwright/stale-folders.md``. Exit 0 (do not block
  our own migration sub-iterates).
- ``status="migrated"``    → structured JSON to stdout + exit 1. The
  AI orchestrator must detect this and stop the session.

Self-healing: when no findings exist on the next run, the report file
is deleted (``unlink(missing_ok=True)``) so the absence of the file is
the canonical "drift-free" signal.

Fail-open: if the scan itself raises (broken symlink, permission
denied, etc.), the hook prints to stderr and exits 0 — never bricks
session start over its own bug.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make shared lib importable regardless of which plugin invokes this hook.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


def _resolve_root() -> Path:
    """Find the Shipwright project root, tolerating subdirectory layouts."""
    try:
        from lib.project_root import resolve_project_root  # type: ignore
        return resolve_project_root()
    except (ImportError, ValueError):
        return Path(os.getcwd())


def main() -> int:
    # Drain stdin (hooks receive a JSON payload we don't need here, but
    # not draining can cause the parent to block).
    try:
        sys.stdin.read()
    except OSError:
        pass

    project_root = _resolve_root()

    try:
        from lib.stale_artifact_detector import hook_main  # type: ignore
    except ImportError as exc:  # pragma: no cover — defensive fail-open
        print(f"[shipwright] drift detector import failed: {exc}", file=sys.stderr)
        return 0

    return hook_main(project_root)


if __name__ == "__main__":
    sys.exit(main())
