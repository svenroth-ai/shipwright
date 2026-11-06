"""Event-folder validation for the churn resolver (issue 978, campaign S3).

``resolve_churn_conflicts._reconcile_events`` validated the legacy log only. With
per-run drop files a behind-main refresh brings in other runs' drops and keeps the
branch's own, so "this run's ``work_completed`` is absent -- the merge dropped it"
must be answered from the ASSEMBLED log (legacy + archive + drops).

Only damage to THIS run's own drop blocks the refresh (DESIGN 10.2, KC8): another run's
damaged drop that already reached main cannot be repaired from this branch (a file that
exists at the merge-base is never edited), so reporting it would stop every branch in
the repo. Nothing here runs for a tree without the folders: the caller keeps today's
legacy-only path byte for byte.
"""

from __future__ import annotations

from pathlib import Path

from lib.events_log import DROPS_DIR, event_files
from lib.events_read import EventLogNotReadable, read_events_assembled, require_readable_for_absence


def has_event_folders(project_root: Path | str) -> bool:
    """True when an archive or drops folder holds at least one event file."""
    return len(event_files(project_root)) > 1


def validate_event_folders(project_root: Path | str, run_id: str | None) -> list[str]:
    """Errors for this run's own drop files; ``run_id`` is looked up across the whole tree."""
    if not run_id:
        return []
    try:
        read = read_events_assembled(Path(project_root))
    except OSError as exc:  # an unreadable legacy log: a structured refusal, never a traceback
        return [f"the event log cannot be read ({exc.__class__.__name__}); the absence of this run's event cannot be concluded"]
    if any(e.get("type") == "work_completed" and e.get("adr_id") == run_id for e in read.records):
        return []
    # A damaged drop of THIS run's own key means "absent" cannot be concluded (KC8).
    try:
        require_readable_for_absence(read, run_id)
    except EventLogNotReadable as exc:
        return [str(exc)]
    return [f"this run's work_completed event (adr_id={run_id}) is absent -- "
            "the merge dropped it; F11 would fail"]


__all__ = ["DROPS_DIR", "has_event_folders", "validate_event_folders"]
