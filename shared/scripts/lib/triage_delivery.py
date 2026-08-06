"""Has a triage decision reached a branch, or is it still in the local buffer?

Split out of :mod:`lib.triage_integrity` once that module held two concerns —
"what could not be read" and "what has not been delivered" — and crossed the
300-line limit. The two are independent questions about the same two files.

**Deliberately a PURE leaf: stdlib only, no intra-package imports.** It works on
record lists a caller has already read, never on paths, so it needs neither
``jsonl_records`` nor ``triage``. That keeps it trivially loadable by
``shared_lib_loader``'s path fallback (ADR-045) and makes the no-import-cycle
constraint hold by construction rather than by care.

WHY THIS EXISTS (IT-1 audit finding 28)
---------------------------------------
``triage_cli``'s ``pendingDelivery`` is derived from two sets that both hold only
``append`` events, so a *status* decision stranded in the gitignored outbox was
structurally invisible: an item dismissed there resolves to a terminal status,
drops out of both the open and deferred lists, and reads as decided-and-done.
There was no surface anywhere saying a decision had not left the clone. Measured
on the live store 2026-08-06: 12 buffered flips, 11 of them invisible.
"""

from __future__ import annotations

import json

__all__ = [
    "format_pending_delivery_notice",
    "undelivered_from_records",
]

#: Ids listed in the operator notice before it summarises the rest.
_NOTICE_ID_CAP = 5


def _canonical(event: dict) -> str:
    """Identity of a status event, independent of key order and spacing.

    Comparing raw physical lines would be brittle: ``churn_merge.dedup_triage_lines``
    exists precisely because same-id, non-identical serializations of one logical
    append occur, so any normalization along the delivery path would forge a false
    "still buffered" on a decision that did reach the branch.
    """
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _ts_key(event: dict) -> str:
    """Mirror of ``triage.read_all_items``' pass-2 ordering key.

    Only a real ISO-8601-Z string participates; anything else sorts earliest, so a
    malformed event can never out-rank a later valid one. Kept identical to the
    reader on purpose — this module must agree with what the board displays, and
    ``test_delivery_check_agrees_with_the_reader_on_the_deciding_event`` is what
    enforces that, rather than this sentence.
    """
    ts = event.get("ts")
    return ts if isinstance(ts, str) else ""


def undelivered_from_records(
    tracked: list[dict], outbox: list[dict], *, applied_statuses,
) -> set[str]:
    """Ids whose **deciding** status event is absent from the tracked records.

    "Deciding" means the event ``read_all_items`` would apply last — ordered by
    ``(ts, file-order)`` with tracked before outbox, exactly as that function orders
    pass 2. Keying on the latest event rather than on *any* event is what makes the
    answer match the board: a superseded flip that was already delivered must not
    mark the item pending, and a newer one that was not must.

    **The reader's two pass-2 FILTERS are mirrored as well, and that is
    load-bearing.** ``read_all_items`` skips a status event whose ``newStatus`` is
    outside ``applied_statuses``, and one whose id has no ``append`` anywhere.
    Measured before this was mirrored: a later out-of-vocabulary event in the
    tracked store out-ranked — and so masked — an older, genuinely buffered
    ``dismissed`` in the outbox, and this function returned an empty set while the
    board showed the flip. That is a false reassurance, the one direction an
    advisory marker must never fail in (Stage-2 code review, high).

    Scope of the claim: absent-from-tracked means the decision has not been
    committed to a branch. It does NOT mean the commit reached ``origin`` — nothing
    here reads a remote.

    During the post-sweep / pre-GC window the same event exists in both files; the
    canonical comparison collapses that to "delivered", which is correct.

    An EMPTY ``applied_statuses`` is rejected rather than honoured: it would filter
    every event out and return "nothing is pending", which is the reassuring
    direction. Requiring the argument stops a caller forgetting it; only this stops
    a caller passing something that silently disables the check (Stage-2 review).
    """
    if not applied_statuses:
        raise ValueError(
            "applied_statuses must be the reader's status vocabulary "
            "(triage.STATUSES); an empty one would report nothing as pending"
        )
    appended = {
        r["id"] for r in tracked + outbox
        if r.get("event") == "append" and isinstance(r.get("id"), str)
    }

    def _statuses(rows: list[dict]) -> list[dict]:
        return [
            r for r in rows
            if r.get("event") == "status"
            and isinstance(r.get("id"), str)
            and r["id"] in appended
            and r.get("newStatus") in applied_statuses
        ]

    delivered = {_canonical(r) for r in _statuses(tracked)}
    ordered = list(enumerate(_statuses(tracked) + _statuses(outbox)))
    ordered.sort(key=lambda pair: (_ts_key(pair[1]), pair[0]))

    deciding: dict[str, dict] = {}
    for _idx, event in ordered:
        deciding[event["id"]] = event
    return {
        item_id for item_id, event in deciding.items()
        if _canonical(event) not in delivered
    }


def format_pending_delivery_notice(item_ids: set[str]) -> str | None:
    """The human listing's one line about decisions not yet committed to a branch.

    A **summary**, not a per-row marker, because the case that matters most is not
    on the list at all: an item dismissed or promoted while its status event stayed
    in the outbox resolves to a terminal status, so it drops out of both sections
    and reads as decided-and-done. A marker can only annotate rows that are still
    rendered; a count can report the ones that vanished. The text therefore says
    "in this store", never "shown here".

    The wording says "not committed to any branch", not "not on origin": all this
    can prove is absence from the git-tracked store.

    Every character is ASCII — ids via ``ascii()`` because they come from a file any
    producer may append to, and the surrounding literal by hand — so the line is
    safe on a Windows cp1252 console without depending on the caller having
    reconfigured the stream. The id list is capped so a deliberately large outbox
    cannot flood the terminal.
    """
    if not item_ids:
        return None
    shown = sorted(item_ids)[:_NOTICE_ID_CAP]
    listed = ", ".join(ascii(i) for i in shown)
    more = f" (+{len(item_ids) - len(shown)} more)" if len(item_ids) > len(shown) else ""
    return (
        f"NOTE: {len(item_ids)} decision(s) in this store are not committed to any "
        f"branch yet - they live only in this clone's gitignored outbox and ship "
        f"with the next iterate PR (some may not appear in the lists above): "
        f"{listed}{more}"
    )
