"""The retired ``gates`` seam — how pre-promotion records are read and superseded.

``spec`` was parked in a sibling ``gates`` object while the cross-repo consumer
rejected any ``reviews`` key outside its pinned five. That pin is gone
(``shipwright-webui`` PR #339 shipped a reader that renders review types it does
not recognise), so ``spec`` is an ordinary review type and nothing writes
``gates`` any more.

Split out of :mod:`lib.review_record_core` at this repo's 300-line file cap, on
a seam that is real rather than convenient: that module owns *how a record is
built and stored today*, this one owns *what an older record needs from us
forever*. Forever is not an exaggeration — 12 git-tracked, never-evicted records
carry ``gates.spec`` and are immutable by design, so this is a permanent
compatibility surface, not a migration window that can later be deleted.

The dependency runs one way — core imports legacy — so there is no cycle.
"""

from __future__ import annotations

from typing import Any

from .review_record_schema import LEGACY_GATE_TYPES, TERMINAL_STATUSES

__all__ = ["LEGACY_SECTION", "WRITE_SECTION", "drop_unanswered_legacy", "read_sections"]

#: Every review pass is WRITTEN here.
WRITE_SECTION = "reviews"

#: Where pre-promotion records put the gate stages.
LEGACY_SECTION = "gates"


def read_sections(review_type: str) -> tuple[str, ...]:
    """Where a type may be FOUND, in precedence order.

    Writing has one destination; reading has two, because a type promoted out of
    the retired seam is still recorded there in every record written before the
    promotion.

    **The order is the answer to "which section is authoritative when both carry
    the type"** — ``reviews`` wins. Both-present is reachable: ``--force`` on a
    legacy record writes into ``reviews`` and leaves a terminal legacy row
    behind. Pinned by ``test_a_reviews_row_wins_over_a_legacy_gates_row``, which
    fails if this tuple is inverted.
    """
    if review_type in LEGACY_GATE_TYPES:
        return (WRITE_SECTION, LEGACY_SECTION)
    return (WRITE_SECTION,)


def drop_unanswered_legacy(
    record: dict[str, Any], review_type: str,
) -> dict[str, Any]:
    """Remove a still-``pending`` legacy row once the real answer is written.

    A record created by a pre-promotion writer carries ``gates: {spec: pending}``
    — that is every run in flight at the rollout. Writing the answer into
    ``reviews`` would otherwise leave the pending row behind, and the consumer
    counts unread passes BY SHAPE, not by key name: any value carrying a
    ``review_type`` under a record key it does not read is counted. It would
    render the ``spec`` row AND append "this run also recorded 1 review pass
    somewhere this version does not read" — telling the reader a pass is missing
    from the list it just showed them (Stage-3 doubt).

    Only a NON-terminal row is dropped, and that destroys no history:
    ``pending`` is the absence of an answer, not an answer. A terminal legacy row
    stays exactly where it is — replacing it needs ``force``, and a recorded
    finding must never be tidied away to make a shape neater.
    """
    legacy = record.get(LEGACY_SECTION)
    if not isinstance(legacy, dict) or review_type not in legacy:
        return record
    if (legacy.get(review_type) or {}).get("status") in TERMINAL_STATUSES:
        return record
    remaining = {k: v for k, v in legacy.items() if k != review_type}
    updated = dict(record)
    if remaining:
        updated[LEGACY_SECTION] = remaining
    else:
        # Drop the key outright rather than leaving `gates: {}` — an empty
        # object is one more unknown record key for a consumer to reason about.
        updated.pop(LEGACY_SECTION, None)
    return updated
