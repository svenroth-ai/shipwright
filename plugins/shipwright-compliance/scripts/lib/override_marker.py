"""The consumption markers of :mod:`compliance_override`: one ``O_EXCL`` file per used entry.

Untracked (under ``.shipwright/locks``), so a ``git restore`` of the override log cannot
revive a used entry. Pure stdlib.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKER_DIR = Path(".shipwright/locks")


def marker(project_root: str | Path, hook: str, at: datetime) -> Path:
    stamp = at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return Path(project_root) / MARKER_DIR / f"consumed-{hook}-{stamp}"


def used(project_root: str | Path, hook: str, at: datetime) -> bool:
    """True when the entry's marker exists -- or cannot be told (fail closed, never open).

    ``Path.exists`` re-raises EACCES on Python 3.11/3.12, which a fail-open hook wrapper
    would turn into an allowed command.
    """
    try:
        return marker(project_root, hook, at).exists()
    except OSError:
        return True


def sweep(markers: Path, keep: timedelta) -> None:
    """Best effort: drop markers older than *keep* (their entry can no longer be in window)."""
    horizon = time.time() - keep.total_seconds()
    try:
        for found in markers.glob("consumed-*"):
            if found.stat().st_mtime < horizon:
                found.unlink(missing_ok=True)
    except OSError:
        pass
