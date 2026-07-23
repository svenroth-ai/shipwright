"""The legacy ``external_*review_state.json`` marker, as a companion of the record.

Two artifacts, deliberately: the **marker** answers *"did this review branch
run?"* for the verifiers (plan resume gate, iterate finalization, compliance
evidence); the **record** (:mod:`lib.review_record`) answers *"what did it
find?"* for the Mission view. This module keeps them written together so they
cannot drift, without collapsing two independent lifecycles into one file.

**Dual-write, not move.** The marker lands at the historic shared path EXACTLY
as before — so no existing consumer anywhere can break — AND as a run-scoped
copy under ``<run_id>/``, which is where the Mission view looks and the only
one that is actually run-specific. Moving it instead would have required every
unknown reader to be found first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .review_marker import build_marker, write_marker
from .review_record_core import ReviewRecordError
from .review_record_ops import repair_companion

__all__ = ["MARKER_TYPES", "repair_markers", "write_markers"]

#: Review types that carry a legacy marker, mapped to the marker's own
#: ``review_mode`` vocabulary (which predates the record's type names).
MARKER_TYPES = {"plan": "iterate", "external_code": "code"}


def write_markers(
    project_root: Path | str,
    run_id: str,
    review_type: str,
    *,
    marker_status: str,
    findings_count: int,
    provider: str | None = None,
    reason: str | None = None,
) -> list[str]:
    """Dual-write the marker. Returns the paths written, run-scoped copy first."""
    marker_mode = MARKER_TYPES.get(review_type)
    marker = build_marker(
        status=marker_status,
        review_type=marker_mode,
        provider=provider,
        reason=reason,
        findings_count=findings_count,
    )
    shared_dir = Path(project_root) / ".shipwright" / "planning" / "iterate"
    return [
        str(write_marker(target, marker, marker_mode))
        for target in (shared_dir / run_id, shared_dir)
    ]


def repair_markers(
    project_root: Path | str,
    run_id: str,
    review_type: str,
    *,
    marker_status: str,
    provider: str | None = None,
    reason: str | None = None,
) -> list[str]:
    """Re-write the marker from the ALREADY-RECORDED entry, leaving it untouched.

    The record is authoritative and immutable, so once it is on disk a failed
    marker write cannot be repaired by re-running ``record`` — that hits the
    immutability guard and exits before reaching the marker — and ``--force``
    would rewrite the authoritative record just to fix a companion file.
    """
    written: list[str] = []

    def rewrite(record: dict[str, Any]) -> None:
        entry = record["reviews"][review_type]
        written.extend(write_markers(
            project_root, run_id, review_type,
            marker_status=marker_status,
            findings_count=int(entry.get("findings_count") or 0),
            provider=provider, reason=reason,
        ))

    _run_repair(project_root, run_id, review_type, rewrite)
    return written


def _run_repair(
    project_root: Path | str,
    run_id: str,
    review_type: str,
    action: Callable[[dict[str, Any]], None],
) -> None:
    if review_type not in MARKER_TYPES:
        raise ReviewRecordError(f"only {sorted(MARKER_TYPES)} carry a legacy marker")
    repair_companion(project_root, run_id, review_type, action)
