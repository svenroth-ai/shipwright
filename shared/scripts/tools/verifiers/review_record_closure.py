"""How a review record is CLOSED — the half of the gate that runs at every complexity.

:mod:`review_record_check` asks whether every type answered; this module asks
whether the answers add up to a reviewed change, and it asks at trivial too.

Two rules, both born of the same hole: a record could close every type
``not_run`` — free-text dispositions and all — and the gate went green at small,
and never even looked at trivial. That is a change nobody reviewed, written down
as if it were a decision.

1. **``self`` is completed, always.** The Self-Review is the one pass the
   iterate SKILL runs unconditionally (Step 7), so a record without it is not a
   record of a lighter process — it is a record of none. Held to the same
   evidence bar as a completed code review (:func:`carries_evidence`): a bare
   ``--status completed`` with ``--from`` omitted is the shape nobody earned.
2. **Every pass that did not run says why in the closed vocabulary.** A
   ``not_run`` / ``not_applicable`` row carries a ``reason_code`` from
   ``lib.reason_codes`` (``review_not_run``). At trivial the one default code is
   ``trivial-auto`` — one ``close-missing`` command closes every type the run
   did not perform, instead of seven hand-written dispositions. Above trivial
   ``trivial-auto`` is refused: from ``small`` up each type names a code that
   fits it. Which code fits is the reviewable claim in the diff — no
   type-to-code matrix is re-encoded here, for the reason the gate's own
   docstring gives for not re-encoding the phase matrix.

The schema already refuses a code outside the vocabulary when the record is
read, so this module only has to ask whether one is present and fits the
complexity.
"""

from __future__ import annotations

from lib.reason_codes import TRIVIAL_AUTO as TRIVIAL_DEFAULT_CODE  # noqa: E402
from lib.review_record import (  # noqa: E402
    RECORDABLE_TYPES,
    STATUS_COMPLETED,
    STATUS_NOT_APPLICABLE,
    STATUS_NOT_RUN,
    entry_for,
)

from .common import CheckResult
from .review_record_floor import CHECK_NAME, carries_evidence

__all__ = ["TRIVIAL_DEFAULT_CODE", "reason_codes_closed", "self_review_recorded"]

_CLOSED = frozenset({STATUS_NOT_RUN, STATUS_NOT_APPLICABLE})
_TOOL = "shared/scripts/tools/record_review_pass.py"


def self_review_recorded(record: dict, run_id: str) -> CheckResult | None:
    """``self`` must be ``completed`` with evidence, at every complexity."""
    entry = entry_for(record, "self")
    status = str(entry.get("status", ""))
    how = (f"`uv run {_TOOL} record --run-id {run_id} --review-type self --status "
           "completed --from self-review --payload-file .shipwright/planning/iterate/"
           f"{run_id}/self-review-payload.json`")
    if status == STATUS_COMPLETED:
        if carries_evidence(entry):
            return None
        return CheckResult(
            CHECK_NAME, False,
            "`self` is recorded completed but carries no evidence the Self-Review "
            "happened: no findings, no provider, no raw excerpt, and no "
            "recorded_by naming an adapter. Re-record it from the checklist "
            f"payload: {how} --force",
        )
    return CheckResult(
        CHECK_NAME, False,
        f"`self` is {status!r} — the Self-Review is the one pass that runs at EVERY "
        "complexity (SKILL.md Step 7), so a record without it describes a change "
        "nobody reviewed, however carefully the other types were closed. Walk the "
        f"checklist and record it: {how}"
        + (" --force" if status in _CLOSED else ""),
    )


def reason_codes_closed(record: dict, complexity: str, run_id: str) -> CheckResult | None:
    """Every ``not_run`` / ``not_applicable`` row carries a code fit for ``complexity``."""
    trivial = complexity == "trivial"
    missing: list[str] = []
    misplaced: list[str] = []
    for review_type in RECORDABLE_TYPES:
        entry = entry_for(record, review_type)
        if entry.get("status") not in _CLOSED:
            continue
        code = entry.get("reason_code")
        if code is None:
            missing.append(review_type)
        elif code == TRIVIAL_DEFAULT_CODE and not trivial:
            misplaced.append(review_type)
    if not missing and not misplaced:
        return None

    fix_one = (f"`uv run {_TOOL} record --run-id {run_id} --review-type <type> "
               "--status not_run|not_applicable --reason-code <code> --force`")
    if trivial:
        return CheckResult(
            CHECK_NAME, False,
            f"{len(missing)} review type(s) closed without a reason_code: "
            f"{', '.join(missing)} — a trivial iterate closes every pass it did not "
            f"run with the ONE default code {TRIVIAL_DEFAULT_CODE!r}, not free text. "
            f"For the next run: `uv run {_TOOL} close-missing --run-id {run_id} "
            f"--status not_applicable --reason-code {TRIVIAL_DEFAULT_CODE}` right "
            f"after `self` is recorded; to repair these rows: {fix_one}",
        )
    parts = []
    if missing:
        parts.append(f"closed without a reason_code: {', '.join(missing)}")
    if misplaced:
        parts.append(f"closed {TRIVIAL_DEFAULT_CODE!r} at {complexity}: {', '.join(misplaced)}")
    return CheckResult(
        CHECK_NAME, False,
        f"from `small` up every pass that did not run names its OWN closed-vocabulary "
        f"code (lib/reason_codes.py, review_not_run) — {'; '.join(parts)}. "
        f"{TRIVIAL_DEFAULT_CODE!r} is the trivial default only. Re-record each row "
        f"with the code that applies: {fix_one} (the codes and when each applies: "
        "iteration-reviews.md → \"Recording each review pass\")",
    )
