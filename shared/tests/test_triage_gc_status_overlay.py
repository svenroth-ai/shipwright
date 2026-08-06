"""Pass-2 status overlay: a damaged status event is skipped WHOLE — audit finding 26.

Both readers of the append-only triage log resolve records in two passes: pass 1
establishes a base record per ``append``, pass 2 overlays ``status`` events. The
overlay used to be PARTIAL in ``triage_gc``: ``status`` was gated on the status enum,
but ``statusBy`` and ``statusReason`` were assigned unconditionally. So a status event
carrying an out-of-enum ``newStatus`` left a person's decision in place while replacing
**who decided it and why**.

That is not cosmetic. ``triage_gc.is_machine_churn`` keys its **delete** decision on
exactly those two fields, so a human dismissal whose actor/reason had been overwritten
by a producer's values becomes indistinguishable from machine churn and is removed by
``apply_gc`` — which FR-01.14 forbids ("every decision a person made stays as the record
of what was decided and why").

``triage.read_all_items`` had the same shape and was fixed first, which left the twins
DIVERGED — a worse state than the symmetric bug, because the SSoT reader and the
compaction reader then disagreed about what a damaged event means. This module fixes the
remaining half and PINS THE TWO TOGETHER so they cannot drift apart silently again.

Each resolver is driven the way production drives it — a real file on disk, not a shared
in-memory list (external plan review, deepseek finding 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent
for _p in (str(_SHARED / "scripts"), str(_SHARED / "scripts" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import triage  # noqa: E402
import triage_gc  # noqa: E402

HEADER = '{"v":1,"schema":"triage","created":"2026-06-08T00:00:00Z"}'
ITEM_ID = "trg-human1"
HUMAN_REASON = "reviewed by hand: won't fix, the caller already guards this"

_APPEND = (
    f'{{"event":"append","id":"{ITEM_ID}","ts":"2026-06-08T00:00:00Z",'
    f'"source":"manual","severity":"low","kind":"bug","title":"t","detail":"d",'
    f'"status":"triage"}}'
)
_HUMAN_DISMISS = (
    f'{{"event":"status","id":"{ITEM_ID}","ts":"2026-06-08T01:00:00Z",'
    f'"newStatus":"dismissed","by":"cli","reason":"{HUMAN_REASON}"}}'
)
#: A producer event whose ``newStatus`` is NOT in the enum. It must be skipped whole.
_DAMAGED = (
    f'{{"event":"status","id":"{ITEM_ID}","ts":"2026-06-08T02:00:00Z",'
    f'"newStatus":"bogus-not-a-status","by":"driftDetector","reason":"driftResolved"}}'
)


def _seed(root: Path, *lines: str) -> Path:
    """Write a real tracked triage log, exactly as both resolvers read it."""
    path = root / ".shipwright" / "triage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([HEADER, *lines]) + "\n", encoding="utf-8", newline="\n")
    return path


def _only(items: list[dict]) -> dict:
    match = [i for i in items if i.get("id") == ITEM_ID]
    assert len(match) == 1, match
    return match[0]


def test_damaged_status_does_not_rewrite_the_human_decision(tmp_path) -> None:
    """AC-4: status, statusBy and statusReason all keep the person's decision."""
    _seed(tmp_path, _APPEND, _HUMAN_DISMISS, _DAMAGED)

    item = _only(triage_gc._resolve_tracked_only(tmp_path))

    assert item["status"] == "dismissed"
    assert item["statusBy"] == "cli"
    assert item["statusReason"] == HUMAN_REASON


def test_damaged_status_cannot_turn_a_human_decision_into_machine_churn(tmp_path) -> None:
    """The consequence that makes AC-4 a data-loss fix rather than tidiness: with the
    partial overlay the producer's ``by``/``reason`` landed on a human dismissal, and
    ``is_machine_churn`` — which reads exactly those two fields — then returned True,
    so the compaction deleted the record of what a person decided."""
    _seed(tmp_path, _APPEND, _HUMAN_DISMISS, _DAMAGED)

    item = _only(triage_gc._resolve_tracked_only(tmp_path))

    assert triage_gc.is_machine_churn(item) is False
    plan = triage_gc.plan_gc(tmp_path)
    # Guard against a vacuous pass: assert the plan actually RESOLVED the item
    # before asserting it is not in the drop set. ``plan_gc`` returns
    # ``drop_ids``/``dropped``/``kept_count``/``total`` — reading a key it does not
    # have would make the next assertion unfalsifiable (Stage-1 spec review).
    assert plan["total"] == 1, plan
    assert ITEM_ID not in plan["drop_ids"], plan


def test_both_resolvers_agree_on_a_damaged_status_event(tmp_path) -> None:
    """AC-5 — the drift pin.

    ``triage.read_all_items`` and ``triage_gc._resolve_tracked_only`` are twin pass-2
    overlays in different modules. Finding 26 existed in both; fixing only one left
    them disagreeing. This test fails if either resolver changes how it treats a
    DAMAGED status event — the cheap substitute for extracting a shared overlay,
    which was kept out of this run so the review diff reads as behaviour change,
    not movement.

    It is NOT a general equivalence guarantee, and must not be read as one: the two
    differ BY DESIGN elsewhere. ``read_all_items`` sorts pass 2 by ``ts`` and also
    overlays ``ts``/``revisitAt``/``promotedTaskId`` plus park expiry, while
    ``_resolve_tracked_only`` applies events in raw file order and overlays none of
    those (the ``ts`` overlay is deliberately not copied). This fixture's file order
    and ``ts`` order coincide, so those differences cannot show up here.
    """
    _seed(tmp_path, _APPEND, _HUMAN_DISMISS, _DAMAGED)

    gc_item = _only(triage_gc._resolve_tracked_only(tmp_path))
    read_item = _only(triage.read_all_items(tmp_path))

    for field in ("status", "statusBy", "statusReason"):
        assert gc_item[field] == read_item[field], (
            f"resolver drift on {field!r}: "
            f"triage_gc={gc_item[field]!r} vs read_all_items={read_item[field]!r}"
        )


def test_non_string_status_is_ignored_by_both_resolvers(tmp_path) -> None:
    """AC-4 for a NON-STRING ``newStatus`` — external code review (openai).

    The reviewer expected `new_status not in triage.STATUSES` to raise ``TypeError``
    on an unhashable value such as ``[]``. It does not: ``triage.STATUSES`` is a
    TUPLE, so membership compares with ``==`` and never hashes. Verified rather than
    assumed. The test is kept anyway, because the claim would become TRUE the day
    someone converts ``STATUSES`` to a set — and it would then abort tracked-log
    compaction rather than ignoring a damaged event.
    """
    for bad in ('[]', '{}', '123', 'null'):
        broken = (
            f'{{"event":"status","id":"{ITEM_ID}","ts":"2026-06-08T02:00:00Z",'
            f'"newStatus":{bad},"by":"driftDetector","reason":"driftResolved"}}'
        )
        _seed(tmp_path, _APPEND, _HUMAN_DISMISS, broken)
        gc_item = _only(triage_gc._resolve_tracked_only(tmp_path))
        read_item = _only(triage.read_all_items(tmp_path))
        for field in ("status", "statusBy", "statusReason"):
            assert gc_item[field] == read_item[field], (bad, field)
        assert gc_item["statusBy"] == "cli", bad
        assert triage_gc.is_machine_churn(gc_item) is False, bad


def test_a_valid_status_event_still_applies(tmp_path) -> None:
    """The guard must not swallow legitimate flips — the regression it could cause."""
    machine_dismiss = (
        f'{{"event":"status","id":"{ITEM_ID}","ts":"2026-06-08T03:00:00Z",'
        f'"newStatus":"dismissed","by":"driftDetector","reason":"driftResolved"}}'
    )
    _seed(tmp_path, _APPEND, machine_dismiss)

    gc_item = _only(triage_gc._resolve_tracked_only(tmp_path))
    read_item = _only(triage.read_all_items(tmp_path))

    assert gc_item["status"] == read_item["status"] == "dismissed"
    assert gc_item["statusBy"] == read_item["statusBy"] == "driftDetector"
    assert triage_gc.is_machine_churn(gc_item) is True
