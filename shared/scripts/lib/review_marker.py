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

try:  # imported as ``lib.review_marker`` (shared/scripts on sys.path)
    from .atomic_write import durable_atomic_write
except ImportError:  # imported as top-level ``review_marker``
    # Plugin call sites put ``shared/scripts/lib`` itself on sys.path — they
    # cannot use the ``lib.`` spelling because their own ``scripts/lib``
    # package shadows it (ADR-045). Both spellings must work: this module is
    # the single authority on review state, and a second copy of that rule is
    # exactly what the gate exists to prevent.
    from atomic_write import durable_atomic_write  # type: ignore[no-redef]

__all__ = [
    "ALLOWED_REVIEW_TYPES",
    "ALLOWED_STATUSES",
    "CODE_REVIEW_STATE_FILE",
    "MARKER_SCHEMA",
    "REVIEW_STATE_FILE",
    "build_marker",
    "evaluate_review_state",
    "marker_filename",
    "write_marker",
]

REVIEW_STATE_FILE = "external_review_state.json"
CODE_REVIEW_STATE_FILE = "external_code_review_state.json"

#: Bumped to 2 when the marker gained per-reviewer ``verdicts`` and the derived
#: ``contradiction``. A marker without the field pre-dates them and is read
#: leniently — it cannot be expected to carry what did not exist when it was
#: written (see :func:`evaluate_review_state`).
MARKER_SCHEMA = 2

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
    verdicts: dict[str, str] | None = None,
    contradiction: dict[str, Any] | None = None,
    contradiction_resolution: str | None = None,
) -> dict[str, Any]:
    """The marker payload. ``self_review_fallback_ran`` is implied by any
    skipped status — the self-review is mandatory, so a skipped external pass
    always fell back to it.

    ``verdicts`` / ``contradiction`` carry what the finding count cannot: which
    way each reviewer came down, and whether the two contradict each other.
    ``contradiction_resolution`` is the operator's decision, and is what clears
    the block in :func:`evaluate_review_state`.
    """
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
        "marker_schema": MARKER_SCHEMA,
        "verdicts": verdicts,
        "contradiction": contradiction,
        "contradiction_resolution": contradiction_resolution,
    }


#: Outcomes of :func:`evaluate_review_state`.
STATE_OK = "ok"
STATE_BLOCK = "block"
#: A ``completed`` external review that recorded no verdicts. Either the
#: marker predates the field, or this run forgot to pass ``--verdict``. The
#: two are indistinguishable from the marker alone, so the caller decides:
#: ``W5`` warns (it may be auditing a plan from before the field existed), the
#: in-session gate blocks (a plan being written now has no excuse, and
#: silently omitting the flag would bypass the disagreement check entirely).
STATE_LEGACY = "legacy"


def evaluate_review_state(marker: dict[str, Any] | None) -> tuple[str, str]:
    """Decide whether a review state is clear to proceed past.

    Returns ``(state, reason)`` where state is :data:`STATE_OK`,
    :data:`STATE_BLOCK` or :data:`STATE_LEGACY`.

    The single authority for that question. The in-session Step 6 gate, the
    ``setup-planning-session`` resume gate and the ``W5`` compliance check all
    call in here, so the three cannot drift into three different definitions
    of "reviewed".

    Blocks on:

    * no marker at all — the review step never ran to completion;
    * a status outside the closed vocabulary;
    * a ``skipped_*`` status with no justification;
    * a disagreement nobody decided — the two reviewers contradict each other,
      or both answered and their verdicts could not be compared. An unreadable
      verdict is not agreement.

    **The disagreement is recomputed from ``verdicts``, not read from the
    stored ``contradiction`` block.** The stored block is a convenience for
    readers; trusting it would let a hand-edited or half-written marker
    (``verdicts`` saying approve/reject, ``contradiction: null``) walk straight
    through every gate. Derived at write time and derived again at read time.
    """
    if not isinstance(marker, dict):
        return STATE_BLOCK, "no review marker — the review step did not run to completion"

    status = str(marker.get("status") or "")
    if status not in ALLOWED_STATUSES:
        return STATE_BLOCK, f"unknown review status {status!r}"

    if status.startswith("skipped_"):
        if not str(marker.get("reason") or "").strip():
            return STATE_BLOCK, f"status={status} but reason is empty (justification required)"
        # A skipped review has no reviewers and therefore no verdicts to weigh.
        return STATE_OK, f"status={status}"

    verdicts = marker.get("verdicts")
    if not isinstance(verdicts, dict) or not verdicts:
        return STATE_LEGACY, (
            "review completed but recorded no reviewer verdicts — a "
            "disagreement between the two could not have been noticed"
        )

    # A `completed` marker where NO leg answered is not a review. It needs no
    # operator resolution — the degraded-review gate owns that condition and
    # fails loudly — but it must not read as reviewed either, or
    # `--verdict gemini=unavailable --verdict openai=unavailable` would clear
    # every gate with nobody having reviewed anything.
    if all(str(v) == "unavailable" for v in verdicts.values()):
        return STATE_BLOCK, (
            "review recorded completed but neither reviewer answered — re-run "
            "the review, or record the appropriate skipped_* status with a reason"
        )

    requires, detail = _disagreement(verdicts)
    if requires and not str(marker.get("contradiction_resolution") or "").strip():
        return STATE_BLOCK, f"unresolved reviewer disagreement: {detail}"

    return STATE_OK, f"status={status}"


def _disagreement(verdicts: dict[str, Any]) -> tuple[bool, str]:
    """``(requires_resolution, reason)`` recomputed from the verdicts alone.

    Imported lazily: this module is imported both as ``lib.review_marker`` and
    as top-level ``review_marker``, and a module-level sibling import would
    have to be spelled two ways (see the atomic_write import above).
    """
    try:
        from .review_verdict import summarize_verdict_pair
    except ImportError:
        from review_verdict import summarize_verdict_pair  # type: ignore[no-redef]

    return summarize_verdict_pair({k: str(v) for k, v in verdicts.items()})


def write_marker(
    planning_dir: Path | str, marker: dict[str, Any], review_type: str | None = None
) -> Path:
    """Write ``marker`` into ``planning_dir``. Durable + atomic so a reader
    never sees a half-written gate state."""
    out_path = Path(planning_dir) / marker_filename(review_type)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(out_path, json.dumps(marker, indent=2) + "\n")
    return out_path
