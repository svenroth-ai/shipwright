"""Session role marker for parallel-iterate discipline.

Two Claude Code sessions running against the same repo (e.g. one in main
repo, one in `.worktrees/<slug>/`) need a designated canonical session
for cleanup/push. The non-canonical session must NOT race the canonical
one with commits/pushes.

This module persists the role to a JSON marker file
(`.shipwright/iterate_session_role.json`) and exposes:

- `read_role(project_root)` — load the marker (or None if missing/invalid)
- `write_role(project_root, role, session_id, worktree_path, notes="")`
  — atomic idempotent write
- `detect_parallel_sessions(project_root)` — scan main repo + every
  `.worktrees/<slug>/.shipwright/iterate_session_role.json`

The companion guard `shared/scripts/checks/check_session_role.py`
consumes this module to gate `git push` from a `secondary` role.

Design notes:
- File is read across sessions and may be edited by the operator,
  so the JSON shape is treated as a producer/consumer boundary
  (touches_io_boundary). Round-trip + BOM/CRLF/non-ASCII/empty
  probes live in `shared/tests/test_session_role.py`.
- Atomic writes via `tmp.replace(target)` mirror the pattern in
  `shared/scripts/lib/autonomous_loop.py`.
- We DO NOT add file locking. Concurrent writes from two
  processes are out of scope — the discipline this module enforces
  IS the locking story (canonical writes; secondary reads).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_ROLES = ("canonical", "secondary")

# File location relative to project root.
MARKER_RELPATH = Path(".shipwright") / "iterate_session_role.json"

# UTF-8 BOM bytes — explicitly stripped on read so a Notepad-saved
# file does not corrupt the first JSON character.
_UTF8_BOM = "﻿"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _marker_path(project_root: Path | str) -> Path:
    return Path(project_root) / MARKER_RELPATH


def read_role(project_root: Path | str) -> dict[str, Any] | None:
    """Read the session-role marker for `project_root`.

    Returns None when the marker file is absent or malformed (default
    permissive — most projects run single-session and shouldn't be
    blocked).

    The reader strips a leading UTF-8 BOM (Notepad / Excel save-as
    artefact) before parsing JSON, and reads with `encoding="utf-8"`
    explicitly to avoid Windows locale fallback (cp1252).
    """
    path = _marker_path(project_root)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    # Strip BOM if present (any line endings — CRLF passes through json).
    if text.startswith(_UTF8_BOM):
        text = text[len(_UTF8_BOM):]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    role = data.get("role")
    if role not in VALID_ROLES:
        return None
    return data


def write_role(
    project_root: Path | str,
    role: str,
    session_id: str,
    worktree_path: str,
    notes: str = "",
) -> dict[str, Any]:
    """Write the session-role marker atomically and idempotently.

    Idempotency rule: if the marker already exists with the same
    `role` AND `worktree_path`, the file is NOT rewritten — preserves
    `set_at` and `set_by_session_id` from the original write so the
    audit trail stays accurate. Notes is allowed to differ silently
    (operator may have annotated).

    Returns the dict that is on disk after the call (either the
    pre-existing one or the freshly written one).
    """
    if role not in VALID_ROLES:
        raise ValueError(
            f"role must be one of {VALID_ROLES!r}, got {role!r}"
        )

    path = _marker_path(project_root)

    existing = read_role(project_root)
    if (
        existing is not None
        and existing.get("role") == role
        and existing.get("worktree_path") == worktree_path
    ):
        return existing

    payload: dict[str, Any] = {
        "role": role,
        "set_at": _now_iso(),
        "set_by_session_id": session_id,
        "worktree_path": worktree_path,
        "notes": notes,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)
    return payload


def detect_parallel_sessions(
    project_root: Path | str,
) -> list[dict[str, Any]]:
    """Return all session-role markers visible from `project_root`.

    Scans:
    1. `<project_root>/.shipwright/iterate_session_role.json` (main repo)
    2. `<project_root>/.worktrees/*/.shipwright/iterate_session_role.json`
       (per-worktree)

    Each entry is the marker dict augmented with a synthetic
    `_marker_path` field (absolute, POSIX-style) so callers can
    print provenance.

    A return list of length >= 2 is the trigger for the SKILL.md B1c
    designation prompt.
    """
    project_root = Path(project_root)
    found: list[dict[str, Any]] = []

    # Main repo marker.
    main = read_role(project_root)
    if main is not None:
        entry = dict(main)
        entry["_marker_path"] = (
            (project_root / MARKER_RELPATH).resolve().as_posix()
        )
        found.append(entry)

    # Worktree markers — `.worktrees/<slug>/.shipwright/...`.
    worktrees_dir = project_root / ".worktrees"
    if worktrees_dir.is_dir():
        for sub in sorted(worktrees_dir.iterdir()):
            if not sub.is_dir():
                continue
            wt_marker = sub / MARKER_RELPATH
            if not wt_marker.exists():
                continue
            wt_role = read_role(sub)
            if wt_role is None:
                continue
            entry = dict(wt_role)
            entry["_marker_path"] = wt_marker.resolve().as_posix()
            found.append(entry)

    return found


# Regex used by callers that want to strip a stray BOM before passing
# bytes through to a third-party JSON parser. Exposed here so the
# probe-test file in shared/tests/ can use the same constant.
def _strip_bom(text: str) -> str:
    """Return `text` without a leading UTF-8 BOM."""
    return text[len(_UTF8_BOM):] if text.startswith(_UTF8_BOM) else text


__all__ = [
    "VALID_ROLES",
    "MARKER_RELPATH",
    "read_role",
    "write_role",
    "detect_parallel_sessions",
]
