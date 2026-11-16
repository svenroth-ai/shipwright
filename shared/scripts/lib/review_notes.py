"""The code-reviewer's top-level ``notes`` string, kept on the ``code`` review row as ``reviewer_notes``.

Notes are NOT findings (never counted, never reaching the autonomous fix loop): the reviewer's "this check could not
run" remarks leave a trace in the record beside the findings. Anything unreadable or not a non-empty string yields
nothing, so a reply without notes records exactly as before.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .review_finding_shape import coerce_text
from .review_findings import ReviewFindingsError, extract_json_payload

__all__ = ["MAX_NOTES", "notes_fields"]

MAX_NOTES = 1000


def notes_fields(args: Any) -> dict[str, str]:
    """``{"reviewer_notes": ...}`` for a completed code-reviewer pass whose reply carries notes, else ``{}``."""
    if args.review_type != "code" or args.review_from != "code-reviewer" or args.status != "completed" or not args.payload_file:
        return {}
    try:
        payload = extract_json_payload(Path(args.payload_file).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ReviewFindingsError):
        return {}
    notes = coerce_text(payload.get("notes") if isinstance(payload, dict) else None, MAX_NOTES)
    return {"reviewer_notes": notes} if notes else {}
