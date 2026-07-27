#!/usr/bin/env python3
"""Archived-scan naming, listing and retention.

Extracted from ``run_scan_and_report.py`` (at its bloat baseline) so the
wrapper can carry the coverage manifest and the scan card without ratcheting.
Behaviour is unchanged.

The archive is what makes a later run-to-run comparison possible at all: two
of these sidecars, each carrying its own coverage manifest.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path

HISTORY_DIRNAME = "history"
RETAIN_PAIRS = 20

# Strict filename pattern for archived scans. User-added or malformed files
# in history/ that don't match are NEVER pruned — they stay where the user
# put them.
SCAN_FILENAME_RE = re.compile(r"^scan-(\d{8}-\d{6}-[0-9a-f]{6})\.(md|json)$")


def new_scan_id(now: datetime) -> str:
    """``scan-YYYYMMDD-HHMMSS-{6 hex}`` — second-grain + uuid for
    collision-safety."""
    ts = now.strftime("%Y%m%d-%H%M%S")
    return f"scan-{ts}-{uuid.uuid4().hex[:6]}"


def list_archived_scans(history_dir: Path) -> list[tuple[str, list[Path]]]:
    """Return list of (scan_id_stem, [files]) ordered newest-first.

    Only files matching SCAN_FILENAME_RE are considered — manual / malformed
    files in the directory are ignored.
    """
    if not history_dir.exists():
        return []

    by_stem: dict[str, list[Path]] = {}
    for child in history_dir.iterdir():
        if not child.is_file():
            continue
        m = SCAN_FILENAME_RE.match(child.name)
        if not m:
            continue
        stem = f"scan-{m.group(1)}"
        by_stem.setdefault(stem, []).append(child)

    # Newest stem first (lexicographic sort works because YYYYMMDD-HHMMSS stems
    # are monotonic).
    return sorted(by_stem.items(), key=lambda kv: kv[0], reverse=True)


def previous_scan_json(history_dir: Path, exclude_scan_id: str | None = None) -> Path | None:
    """Newest archived ``*.json`` sidecar, skipping ``exclude_scan_id``.

    This is the "previous run" a comparison is drawn against. Deliberately has
    no caller in this half — the run-to-run comparison that consumes it lands in
    Part 2; it lives here because the archive it reads is this module's.
    """
    for stem, files in list_archived_scans(history_dir):
        if exclude_scan_id is not None and stem == exclude_scan_id:
            continue
        for f in files:
            if f.suffix == ".json":
                return f
    return None


def prune_history(history_dir: Path, retain: int = RETAIN_PAIRS) -> int:
    """Delete archived scans beyond the retain limit; return count removed."""
    grouped = list_archived_scans(history_dir)
    to_delete = grouped[retain:]
    removed = 0
    for _stem, files in to_delete:
        for f in files:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed
