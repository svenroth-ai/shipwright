"""Delivery visibility — IT-1 audit finding 28.

Part of iterate-2026-08-06-p2-19c-corruption-absence (card ``trg-8652bf24``).
Split from ``test_triage_reader_integrity.py`` when that file outgrew the 300-line
limit, along the same seam as the modules under test: lock scope stays there,
delivery visibility lives here.

``pendingDelivery`` is computed from two sets that both contain only ``append``
events, so a status decision stranded in the gitignored outbox is structurally
invisible: the board renders it identically to one that reached a branch. Measured
on the live store at the start of this run: 12 buffered flips, 11 invisible.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402
from lib.jsonl_records import CorruptFragment  # noqa: E402
from lib.triage_contract import build_listing  # noqa: E402
from lib.triage_integrity import undelivered_status_ids  # noqa: E402
from triage import STATUSES  # noqa: E402


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path



_APPEND = {
    "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
    "title": "t", "status": "triage", "severity": "low", "kind": "bug",
    "source": "manual", "detail": "d",
}
_FLIP = {
    "event": "status", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "newStatus": "dismissed", "by": "webui", "reason": "done",
}


def _split_store(tmp_path: Path, *, tracked_extra: str = "") -> tuple[Path, Path]:
    tracked = tmp_path / "triage.jsonl"
    outbox = tmp_path / "triage.outbox.jsonl"
    tracked.write_bytes(
        (_j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + tracked_extra).encode()
    )
    outbox.write_bytes((_j(_FLIP) + "\n").encode())
    return tracked, outbox


def test_status_flip_only_in_the_outbox_is_undelivered(tmp_path: Path) -> None:
    tracked, outbox = _split_store(tmp_path)
    assert undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES) == {"trg-good0001"}


def test_status_flip_present_in_the_tracked_store_is_delivered(tmp_path: Path) -> None:
    tracked, outbox = _split_store(tmp_path, tracked_extra=_j(_FLIP) + "\n")
    assert undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES) == set()


def test_delivery_check_is_canonical_not_byte_literal(tmp_path: Path) -> None:
    """A re-serialization with different key order must not forge a false pending.

    The sweep copies lines verbatim today, but ``churn_merge.dedup_triage_lines``
    exists because same-id non-identical lines happen. Comparing raw text would
    make any normalization report a delivered decision as still buffered.
    """
    reordered = {k: _FLIP[k] for k in reversed(list(_FLIP))}
    tracked, outbox = _split_store(tmp_path, tracked_extra=_j(reordered) + "\n")
    assert undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES) == set()


def test_only_the_deciding_status_event_counts(tmp_path: Path) -> None:
    """A superseded, already-delivered flip must not mark the item pending.

    The field answers "has the decision the board is SHOWING reached origin", so
    it is keyed on the latest event, not on any event.
    """
    older = {**_FLIP, "ts": "2026-01-01T12:00:00Z", "newStatus": "snoozed"}
    tracked = tmp_path / "triage.jsonl"
    outbox = tmp_path / "triage.outbox.jsonl"
    tracked.write_bytes(
        (_j({"v": 1}) + "\n" + _j(_APPEND) + "\n"
         + _j(older) + "\n" + _j(_FLIP) + "\n").encode()
    )
    outbox.write_bytes((_j(older) + "\n").encode())
    assert undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES) == set()


def test_out_of_vocabulary_tracked_event_cannot_mask_a_buffered_flip(
    tmp_path: Path,
) -> None:
    """The Stage-2 high finding: mirroring the ordering is not mirroring the reader.

    ``read_all_items`` pass 2 SKIPS a status event whose ``newStatus`` is outside
    ``STATUSES``. Before this filter was mirrored, such an event — later by ts, and
    sitting in the tracked store — out-ranked and masked a genuinely buffered
    ``dismissed`` in the outbox, so the board showed the flip while the delivery
    check reported nothing pending. A false reassurance, the one direction this
    marker must never fail in.
    """
    unknown = {**_FLIP, "ts": "2026-01-03T00:00:00Z", "newStatus": "parked"}
    tracked, outbox = _split_store(tmp_path, tracked_extra=_j(unknown) + "\n")

    project_view = undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES)
    assert project_view == {"trg-good0001"}


def test_a_status_event_with_no_append_is_not_named(tmp_path: Path) -> None:
    """The other pass-2 filter: an orphan status is dropped by the reader.

    Naming it would point the operator at an item no surface shows.
    ``lib/triage_validate.py`` already records orphan-status as a known class.
    """
    orphan = {**_FLIP, "id": "trg-orphan01"}
    tracked = tmp_path / "triage.jsonl"
    outbox = tmp_path / "triage.outbox.jsonl"
    tracked.write_bytes((_j({"v": 1}) + "\n" + _j(_APPEND) + "\n").encode())
    outbox.write_bytes((_j(orphan) + "\n").encode())

    assert undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES) == set()


def test_delivery_check_agrees_with_the_reader_on_the_deciding_event(
    tmp_path: Path,
) -> None:
    """Converts "kept identical to the reader" from a comment into a gate.

    ``_ts_key`` is duplicated in `lib.triage_delivery` because the no-import-cycle
    constraint forbids importing `triage`. The duplication is justified, but the
    agreement it asserts is load-bearing for the whole "deciding event" claim, so
    it needs a test rather than a docstring line.
    """
    project = _project(tmp_path)
    malformed_ts = {**_FLIP, "ts": 12345, "newStatus": "promoted"}
    later_valid = {**_FLIP, "ts": "2026-01-05T00:00:00Z", "newStatus": "snoozed"}
    tracked = triage._triage_path(project)
    outbox = triage._outbox_path(project)
    tracked.write_bytes(
        (_j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(malformed_ts) + "\n").encode()
    )
    outbox.write_bytes((_j(later_valid) + "\n").encode())

    board = {i["id"]: i for i in triage.read_all_items(project)}["trg-good0001"]
    pending = undelivered_status_ids(tracked, outbox, applied_statuses=STATUSES)

    # The reader applied the later VALID event; the delivery check must agree that
    # THAT is the deciding one, and that it is the buffered one.
    assert board["status"] == "snoozed"
    assert pending == {"trg-good0001"}


def test_an_empty_status_vocabulary_is_refused(tmp_path: Path) -> None:
    """Requiring the argument stops a caller FORGETTING it, not passing an empty one.

    An empty vocabulary filters every event out and returns "nothing is pending" —
    the reassuring direction, i.e. the defect this whole surface exists to close
    (Stage-2 code review).
    """
    import pytest

    tracked, outbox = _split_store(tmp_path)
    with pytest.raises(ValueError, match="applied_statuses"):
        undelivered_status_ids(tracked, outbox, applied_statuses=())


def test_a_missing_outbox_means_nothing_is_pending(tmp_path: Path) -> None:
    tracked = tmp_path / "triage.jsonl"
    tracked.write_bytes((_j({"v": 1}) + "\n" + _j(_APPEND) + "\n").encode())
    assert undelivered_status_ids(tracked, tmp_path / "absent.jsonl", applied_statuses=STATUSES) == set()


def test_listing_always_carries_a_boolean_pending_status_delivery() -> None:
    """Always present, both sections — never a second shape variant."""
    item = {"id": "trg-good0001", "status": "triage", "severity": "low"}
    other = {"id": "trg-other001", "status": "snoozed", "severity": "low"}
    payload = build_listing(
        [item], [other],
        tracked_ids={"trg-good0001", "trg-other001"},
        outbox_ids=set(),
        severity_rank={"low": 3},
        undelivered_status_ids={"trg-good0001"},
        undelivered_amend_ids=set(),
        corruption=[],
    )
    assert payload["open"][0]["pendingStatusDelivery"] is True
    assert payload["open"][0]["pendingAmendDelivery"] is False
    assert payload["deferred"][0]["pendingStatusDelivery"] is False
    assert payload["contractVersion"] == 2
    # The envelope carries the same fact for rows that are NOT rendered.
    assert payload["undeliveredDecisions"]["count"] == 1
    assert payload["undeliveredDecisions"]["ids"] == ["trg-good0001"]


def test_pending_delivery_field_is_unchanged() -> None:
    """The existing field keeps its append-residence meaning — no redefinition."""
    item = {"id": "trg-good0001", "status": "triage", "severity": "low"}
    payload = build_listing(
        [item], [],
        tracked_ids=set(),
        outbox_ids={"trg-good0001"},
        severity_rank={"low": 3},
        undelivered_status_ids=set(),
        undelivered_amend_ids=set(),
        corruption=[],
    )
    assert payload["open"][0]["pendingDelivery"] is True
    assert payload["open"][0]["pendingStatusDelivery"] is False
    assert payload["open"][0]["pendingAmendDelivery"] is False


# ---------------------------------------------------------------------------
# The envelope's corruption block (AC2's machine-readable half)
# ---------------------------------------------------------------------------

def _listing(corruption: list) -> dict:
    return build_listing(
        [], [], tracked_ids=set(), outbox_ids=set(),
        severity_rank={"low": 3}, undelivered_status_ids=set(),
        undelivered_amend_ids=set(),
        corruption=corruption,
    )


def test_a_clean_store_reports_an_empty_corruption_block() -> None:
    """Always present, so a consumer never has to distinguish absent from clean."""
    block = _listing([])["corruption"]
    assert block == {"count": 0, "truncated": False, "spans": []}


def test_corruption_block_carries_shape_never_content(tmp_path: Path) -> None:
    """The undecodable bytes must not reach a JSON consumer either."""
    frag = CorruptFragment(path=str(tmp_path / "triage.jsonl"), line_no=7,
                           text='\x1b[31mDANGER\x07{"broken":')
    span = _listing([frag])["corruption"]["spans"][0]
    assert span == {"path": "triage.jsonl", "line": 7, "bytes": len(frag.text)}
    assert "DANGER" not in json.dumps(span)


def test_corruption_block_is_capped_and_says_so() -> None:
    """A deliberately malformed log must not inflate the response without bound.

    `truncated` is what stops a capped list being read as a complete one.
    """
    frags = [CorruptFragment(path="t.jsonl", line_no=i, text="x") for i in range(50)]
    block = _listing(frags)["corruption"]
    assert block["count"] == 50
    assert block["truncated"] is True
    assert len(block["spans"]) < 50
