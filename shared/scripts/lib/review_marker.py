"""The external-review **gate marker** — ``external_*review_state.json``.

Extracted verbatim from ``shared/scripts/checks/mark-review-state.py`` so that
``record_review_pass.py`` can write the marker without duplicating its shape.
Behaviour is unchanged; the script is now a thin CLI over this module.

**Marker vs. record — two artifacts, deliberately.** The marker answers *"did
this review branch run?"* and is consumed by verifiers (plan resume gate,
iterate finalization, compliance evidence). The per-run
:mod:`lib.review_record` answers *"what did the review find?"* and is consumed
by the Mission view. They have different lifetimes (``/shipwright-plan``
overwrites its own marker on its own schedule), different immutability rules,
and different readers, so collapsing them into one file would couple two
lifecycles that are independent on purpose.

``review_mode`` is named that, NOT ``review_type``, to stay clear of the
build-side dashboard's ``review_type`` taxonomy (``self-review`` /
``full-review`` / ``external-review``). The two share no semantics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_write import durable_atomic_write

__all__ = [
    "ALLOWED_REVIEW_TYPES",
    "ALLOWED_STATUSES",
    "CODE_REVIEW_STATE_FILE",
    "REVIEW_STATE_FILE",
    "build_marker",
    "marker_filename",
    "write_marker",
]

REVIEW_STATE_FILE = "external_review_state.json"
CODE_REVIEW_STATE_FILE = "external_code_review_state.json"

ALLOWED_STATUSES = frozenset({
    "completed",
    "skipped_user_opt_out",
    "skipped_config_disabled",
})

ALLOWED_REVIEW_TYPES = ("plan", "iterate", "code")


def marker_filename(review_type: str | None) -> str:
    """``code`` writes the code-review cascade's own marker; everything else
    writes the plan/iterate marker. The two gates are independent and must
    never collide."""
    return CODE_REVIEW_STATE_FILE if review_type == "code" else REVIEW_STATE_FILE


def build_marker(
    *,
    status: str,
    review_type: str | None = None,
    provider: str | None = None,
    reason: str | None = None,
    findings_count: int = 0,
    self_review_fallback_ran: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """The marker payload. ``self_review_fallback_ran`` is implied by any
    skipped status — the self-review is mandatory, so a skipped external pass
    always fell back to it."""
    return {
        "status": status,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "findings_count": findings_count,
        "self_review_fallback_ran": (
            self_review_fallback_ran
            or status in {"skipped_user_opt_out", "skipped_config_disabled"}
        ),
        "reason": reason,
        "review_mode": review_type,
    }


def write_marker(
    planning_dir: Path | str, marker: dict[str, Any], review_type: str | None = None
) -> Path:
    """Write ``marker`` into ``planning_dir``. Durable + atomic so a reader
    never sees a half-written gate state."""
    out_path = Path(planning_dir) / marker_filename(review_type)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(out_path, json.dumps(marker, indent=2) + "\n")
    return out_path
