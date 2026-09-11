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
    "foreign_undelivered_amends_from_records",
    "foreign_undelivered_from_records",
    "format_pending_delivery_notice",
    "undelivered_amends_from_records",
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


def foreign_undelivered_from_records(
    tracked: list[dict], outbox: list[dict], foreign: list[tuple[str, list[dict]]],
    *, applied_statuses,
) -> dict[str, str]:
    """Ids whose TRUE deciding status event — across tracked, outbox AND every
    sibling worktree's tracked log — resides ONLY in one of those siblings.
    Maps each such id to the branch that holds it.

    ``foreign`` is ``(branch, records)`` pairs, e.g. from
    :func:`lib.triage_cross_tree.foreign_records_by_branch`. Cross-tree
    counterpart of :func:`undelivered_from_records` (kept separate so that
    function's own tests/callers stay untouched) — same canonical-delivered
    check, extended with a third source ordered tracked, outbox, then foreign,
    by ``(ts, position)`` — delivery facts, not resolved status, so this
    deliberately skips `read_all_items`'s local-wins rule (see
    :mod:`lib.triage_cross_tree`'s docstring). An id whose deciding
    event is already canonically present in ``tracked`` (e.g. after that
    branch merged) is absent here even if a stale copy lingers in a foreign
    log and technically wins a timestamp tie by position — see the canonical
    check below, mirroring :func:`undelivered_from_records`'s own.
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

    local = [(None, r) for r in _statuses(tracked) + _statuses(outbox)]
    foreign_events = [
        (branch, r) for branch, records in foreign for r in _statuses(records)
    ]
    ordered = list(enumerate(local + foreign_events))
    ordered.sort(key=lambda pair: (_ts_key(pair[1][1]), pair[0]))

    deciding: dict[str, tuple[str | None, dict]] = {}
    for _idx, (branch, event) in ordered:
        deciding[event["id"]] = (branch, event)

    # A tied timestamp is resolved by POSITION, same as read_all_items (foreign
    # sorts after local) — so a tracked copy can still lose the tie to its own
    # foreign twin. The canonical check answers "delivered" regardless of which
    # physical copy the tiebreak picked.
    delivered = {_canonical(r) for r in _statuses(tracked)}
    return {
        item_id: branch for item_id, (branch, event) in deciding.items()
        if branch is not None and _canonical(event) not in delivered
    }


def foreign_undelivered_amends_from_records(
    tracked: list[dict], foreign: list[tuple[str, list[dict]]], *, is_valid_amend,
) -> dict[str, str]:
    """Ids with a valid amend present ONLY in a sibling worktree's tracked log
    (never delivered to THIS tree's own tracked store), mapped to the branch
    that holds it. Cross-tree counterpart of
    :func:`undelivered_amends_from_records` — amends accumulate, so this
    checks canonical presence in ``tracked``, not "most recent wins".

    First sibling wins an id already claimed by an earlier one in ``foreign``
    (an id amended on two branches at once is a pre-existing conflict this
    function reports, not resolves).
    """
    tracked_append_ids = {
        r["id"] for r in tracked
        if r.get("event") == "append" and isinstance(r.get("id"), str)
    }

    def _amends(rows: list[dict]) -> list[dict]:
        return [
            r for r in rows
            if r.get("event") == "amend"
            and isinstance(r.get("id"), str)
            and r["id"] in tracked_append_ids
            and is_valid_amend(r)
        ]

    delivered = {_canonical(r) for r in _amends(tracked)}
    out: dict[str, str] = {}
    for branch, records in foreign:
        for r in _amends(records):
            if _canonical(r) not in delivered:
                out.setdefault(r["id"], branch)
    return out


def undelivered_amends_from_records(
    tracked: list[dict], outbox: list[dict], *, is_valid_amend,
) -> set[str]:
    """Ids with a valid amend that is present only in the outbox.

    Amend overlays accumulate: unlike a status flip, each valid correction can
    affect the resolved card. A tracked copy of the same canonical event marks
    that correction delivered; a later amendment does not erase an earlier
    undelivered field change. Invalid and orphan amends are ignored exactly as
    ``triage.read_all_items`` ignores them.
    """
    tracked_append_ids = {
        r["id"] for r in tracked
        if r.get("event") == "append" and isinstance(r.get("id"), str)
    }

    def _amends(rows: list[dict]) -> list[dict]:
        return [
            r for r in rows
            if r.get("event") == "amend"
            and isinstance(r.get("id"), str)
            and r["id"] in tracked_append_ids
            and is_valid_amend(r)
        ]

    delivered = {_canonical(r) for r in _amends(tracked)}
    return {
        event["id"] for event in _amends(outbox)
        if _canonical(event) not in delivered
    }

def format_pending_delivery_notice(
    item_ids: set[str], *, origin_branches: dict[str, str] | None = None,
) -> str | None:
    """The human listing's one line about decisions not yet committed here.

    A **summary**, not a per-row marker, because the case that matters most is not
    on the list at all: an item dismissed or promoted while its status event stayed
    buffered resolves to a terminal status, dropping out of both sections and
    reading as decided-and-done. A marker can only annotate rows still rendered;
    a count can report the ones that vanished — hence "in this store", never "shown here".

    The wording says "not committed to any branch" / "not yet merged here", never
    "not on origin" or "reached origin": all this can prove is what this reading
    tree's own tracked store, and its known siblings, currently hold — and never a
    live risk to the resolution shown above: `read_all_items`'s local-wins rule
    (:mod:`lib.triage_cross_tree`) bars a sibling's timestamp from ever reopening a
    local decision, so reversing one shown here takes an actual merge, not a race.

    ``origin_branches`` (optional) names, for an id whose decision this reader
    found on a SIBLING worktree rather than in its own gitignored outbox, which
    branch holds it (see :mod:`lib.triage_cross_tree`). An id absent from it is
    the original, plainer case — still only in this clone's outbox.

    Every character is ASCII — ids/branch names via ``ascii()`` (producer-supplied
    text), the rest by hand — safe on a Windows cp1252 console without a
    reconfigured stream. The id list is capped so a large outbox cannot flood it.
    """
    if not item_ids:
        return None
    origin_branches = origin_branches or {}
    shown = sorted(item_ids)[:_NOTICE_ID_CAP]

    def _label(item_id: str) -> str:
        branch = origin_branches.get(item_id)
        if branch is None:
            return ascii(item_id)
        return f"{ascii(item_id)} (on {ascii(branch)}, not yet merged here)"

    listed = ", ".join(_label(i) for i in shown)
    more = f" (+{len(item_ids) - len(shown)} more)" if len(item_ids) > len(shown) else ""
    return (
        f"NOTE: {len(item_ids)} decision(s) in this store are not committed to any "
        f"branch yet, or sit on a branch this project has not merged (some may not "
        f"appear in the lists above): {listed}{more}"
    )
