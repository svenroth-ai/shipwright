#!/usr/bin/env python3
"""Iterate Stop hook — runs shared handoff + finalize_iterate as fallback.

Delegates to the shared generate_handoff_on_stop first (preserving
canon-marker skip logic from iterate 12.1), then checks whether
finalize_iterate already ran during this session.  If not, runs it as
a repair pass.

This hook imports modules directly (no subprocess) to avoid stdin
payload forwarding issues (external review Finding 7).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
sys.path.insert(0, str(_SHARED_SCRIPTS))


def _get_latest_run_id(project_root: Path) -> str | None:
    """Return the most recent iterate run_id, or None if no history exists.

    Reads from the merged legacy-array + file-per-iterate store via
    ``lib.iterate_entry.last_iterate_entry``. Falling back silently when
    the store is missing (fresh project, pre-adopt repo) is intentional —
    this function feeds a freshness gate and must never crash.
    """
    try:
        from lib.iterate_entry import last_iterate_entry

        entry = last_iterate_entry(project_root)
    except Exception:
        return None
    if not entry:
        return None
    run_id = entry.get("run_id")
    return run_id if isinstance(run_id, str) else None


def _dashboard_reflects_run_id(project_root: Path, run_id: str) -> bool:
    """Check if build_dashboard.md already contains the current run_id."""
    dashboard = project_root / ".shipwright" / "agent_docs" / "build_dashboard.md"
    if not dashboard.exists():
        return False
    try:
        return run_id in dashboard.read_text(encoding="utf-8")
    except OSError:
        return False


def main() -> int:
    # Consume stdin (hook protocol)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    # 1. Run the shared handoff-on-stop (same as all other plugins)
    try:
        from hooks.generate_handoff_on_stop import main as handoff_main
        # Re-feed empty stdin since we consumed it
        original_stdin = sys.stdin
        sys.stdin = open(os.devnull) if os.name != "nt" else __import__("io").StringIO("{}")
        try:
            handoff_main()
        finally:
            sys.stdin = original_stdin
    except Exception as exc:
        print(f"[iterate_stop_finalize] handoff failed: {exc}", file=sys.stderr)

    # 2. Resolve project root
    try:
        from lib.project_root import resolve_project_root
        project_root = resolve_project_root()
    except (ImportError, ValueError):
        return 0

    # 3. Freshness gate — skip if finalize_iterate already ran
    run_id = _get_latest_run_id(project_root)
    if not run_id:
        return 0

    if _dashboard_reflects_run_id(project_root, run_id):
        return 0

    # 4. Repair pass — finalize_iterate was not run during this session
    try:
        from tools.finalize_iterate import run as finalize_run
        result = finalize_run(project_root, run_id=run_id)
        print(f"[iterate_stop_finalize] repair pass completed: "
              f"{sum(1 for s in result['steps'].values() if s.get('written'))} artifacts updated",
              file=sys.stderr)
    except Exception as exc:
        print(f"[iterate_stop_finalize] repair failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
