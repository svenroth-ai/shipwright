#!/usr/bin/env python3
"""SessionStart hook: scan project root for stale legacy artifact dirs.

Wired in every plugin's ``hooks/hooks.json`` as the third SessionStart
hook (after ``capture_session_id.py`` and ``phase_session_start.py``).

Behavior per ``ARTIFACT_MIGRATIONS`` entry (always exit 0 — a
SessionStart hook cannot block a session):
- ``status="in_progress"`` → warn-only stderr notice + drift report
  written to ``.shipwright/stale-folders.md``.
- ``status="migrated"``    → warn-only: a schema-valid
  ``additionalContext`` payload on stdout delivers the drift + ``git mv``
  remediation to the model (the channel SessionStart actually reads),
  plus a stderr notice + the report. (Historically documented as an
  ``exit 1`` "hard-gate"; that was inert — WP4.)

Self-healing: when no findings exist on the next run, the report file
is deleted (``unlink(missing_ok=True)``) so the absence of the file is
the canonical "drift-free" signal.

Fail-open: if the scan itself raises (broken symlink, permission
denied, etc.), the hook prints to stderr and exits 0 — never bricks
session start over its own bug.
"""
from __future__ import annotations

import json
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


def _session_id_from(payload: object) -> str:
    """SessionStart payload ``session_id`` → claim key (env / 'unknown' fallback)."""
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    return (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip() or "unknown"


def main() -> int:
    # Read the SessionStart payload (also drains stdin so the parent never
    # blocks). The payload carries session_id, used as the dedup claim key.
    payload: object = {}
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            payload = json.loads(raw)
    except (OSError, ValueError):
        payload = {}

    project_root = _resolve_root()

    try:
        from lib.stale_artifact_detector import hook_main  # type: ignore
    except ImportError as exc:  # pragma: no cover — defensive fail-open
        print(f"[shipwright] drift detector import failed: {exc}", file=sys.stderr)
        return 0

    # Once-per-SessionStart dedup. This hook fires ~12× per SessionStart with
    # IDENTICAL inputs — it scans project_root and never reads CLAUDE_PLUGIN_ROOT
    # — so 11 of the 12 scans + any additionalContext drift-remediation message
    # are pure duplication. The 'sessionstart-drift' key is distinct from
    # capture_session_id's injection claim. Fail-open + unknown-session handling
    # in the shared helper.
    from lib.event_once import claim_once_for_event
    if not claim_once_for_event(project_root, "sessionstart-drift", _session_id_from(payload)):
        return 0

    return hook_main(project_root)


if __name__ == "__main__":
    sys.exit(main())
