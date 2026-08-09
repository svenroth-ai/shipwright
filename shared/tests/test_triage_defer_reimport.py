"""Re-import suppression while an entry is parked — `triage.py`.

iterate-2026-08-01-triage-defer-lifecycle, split from
`test_triage_defer_store.py` to keep both files inside the 300-line budget.
The defect these pin: the idempotent dedup scan suppressed only against an OPEN
match, so parking a machine-raised finding produced a duplicate open entry on
the very next import PLUS a permanent parked one — which made parking close to
a no-op for exactly the findings most likely to be parked.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import (  # noqa: E402
    append_triage_item,
    append_triage_item_idempotent,
    mark_status,
    read_all_items,
)

PAST = "2020-01-01"
FUTURE = "2099-01-01"


def _item(project: Path, **over) -> str:
    kw = dict(source="github", severity="high", kind="bug",
              title="a finding", detail="d")
    kw.update(over)
    return append_triage_item(project, **kw)


# ---------------------------------------------------------------------------
# AC-4 / AC-5 / AC-28 — re-import suppression
# ---------------------------------------------------------------------------

def _reimport(project: Path, **over) -> str | None:
    kw = dict(source="github", severity="high", kind="bug", title="a finding",
              detail="d", dedup_key="gh-security:acme/foo", match_commit=False)
    kw.update(over)
    return append_triage_item_idempotent(project, **kw)


def test_idempotent_append_uses_one_instant_captured_inside_its_lock(
    tmp_path: Path, monkeypatch,
) -> None:
    stamp = datetime(2099, 9, 1, 0, 0, tzinfo=timezone.utc)
    depth = []
    calls = []

    class TracingLock:
        def __init__(self, _path):
            pass

        def __enter__(self):
            depth.append(True)

        def __exit__(self, *_exc):
            depth.pop()

    def clock():
        assert depth, "clock was read before the store lock"
        calls.append(stamp)
        return stamp

    monkeypatch.setattr(triage, "_load_file_lock_cls", lambda: TracingLock)
    monkeypatch.setattr(triage._load_triage_defer(), "now_utc", clock)
    item_id = _reimport(tmp_path, window_seconds=60)

    [event] = [json.loads(line) for line in (
        tmp_path / ".shipwright" / "triage.jsonl"
    ).read_text(encoding="utf-8").splitlines() if '"event":"append"' in line]
    assert calls == [stamp]
    assert (event["id"], event["ts"], event["originalTs"]) == (
        item_id, "2099-09-01T00:00:00Z", "2099-09-01T00:00:00Z",
    )


def test_a_park_that_is_not_due_suppresses_the_re_import(
    tmp_path: Path,
) -> None:
    """The defect this whole part exists to fix: before, the dedup scan only
    suppressed against an OPEN match, so parking a machine-raised finding
    yielded a duplicate open entry PLUS a permanent parked one."""
    first = _reimport(tmp_path)
    mark_status(tmp_path, first, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    assert _reimport(tmp_path) is None
    assert len(read_all_items(tmp_path)) == 1


def test_the_park_beats_the_recency_window(tmp_path: Path) -> None:
    """A one-second window would normally let the finding re-fire at once. The
    park's own date is its window, so it must not."""
    first = _reimport(tmp_path)
    mark_status(tmp_path, first, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    assert _reimport(tmp_path, window_seconds=0) is None


def test_an_expired_park_also_suppresses_because_it_is_open_again(
    tmp_path: Path,
) -> None:
    """AC-5: expiry re-opens the original; it never licenses a duplicate,
    even when that original is older than the producer's recency window."""
    first = _reimport(tmp_path)
    mark_status(tmp_path, first, new_status="snoozed", by="cli",
                reason="later", revisit_at=PAST)
    assert _reimport(tmp_path, window_seconds=0) is None


def test_revisit_bytes_on_an_append_cannot_masquerade_as_an_expired_park(
    tmp_path: Path,
) -> None:
    """Only a valid snoozed status event can establish revisit semantics."""
    first = _reimport(tmp_path)
    store = tmp_path / ".shipwright" / "triage.jsonl"
    records = [json.loads(line) for line in store.read_text(
        encoding="utf-8").splitlines()]
    append = next(row for row in records if row.get("event") == "append")
    append["revisitAt"] = PAST
    append["ts"] = append["originalTs"] = "2020-01-01T00:00:00Z"
    store.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in records)
        + "\n",
        encoding="utf-8",
    )

    [resolved] = read_all_items(tmp_path)
    assert (resolved["revisitAt"], resolved["revisitDue"]) == (None, False)
    second = _reimport(tmp_path, window_seconds=0)
    assert second is not None and second != first


def test_a_dismissed_finding_does_not_reimport_under_a_new_id(
    tmp_path: Path,
) -> None:
    """A matching dismissal remains durable across a compliance re-import."""
    first = _reimport(tmp_path)
    mark_status(tmp_path, first, new_status="dismissed", by="cli", reason="no")
    second = _reimport(tmp_path)
    assert second is None
    assert [item["id"] for item in read_all_items(tmp_path)] == [first]


def test_a_park_does_not_suppress_a_different_finding(tmp_path: Path) -> None:
    """Suppression identity is unchanged — source + dedupKey — so a park on one
    finding must not silence its neighbour (external review, round 2 #5)."""
    first = _reimport(tmp_path)
    mark_status(tmp_path, first, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    assert _reimport(tmp_path, dedup_key="gh-security:acme/other") is not None


def test_a_dismissal_living_only_in_the_outbox_suppresses_too(tmp_path: Path) -> None:
    outbox = tmp_path / ".shipwright" / "triage.outbox.jsonl"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text(json.dumps({
        "event": "append", "id": "trg-outbox-dismissed", "ts": "2026-06-10T00:00:00Z",
        "originalTs": "2026-06-10T00:00:00Z", "source": "github", "severity": "high",
        "kind": "bug", "title": "outbox finding", "detail": "d",
        "dedupKey": "gh-security:acme/foo", "status": "dismissed",
    }) + "\n", encoding="utf-8")
    assert _reimport(tmp_path) is None

def test_a_park_living_only_in_the_outbox_suppresses_too(
    tmp_path: Path,
) -> None:
    """The scan runs over the tracked ∪ outbox union, so a park recorded in the
    gitignored buffer must suppress a tracked re-import just the same."""
    outbox = tmp_path / ".shipwright" / "triage.outbox.jsonl"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text(
        json.dumps({
            "event": "append", "id": "trg-outbox01",
            "ts": "2026-06-10T00:00:00Z", "originalTs": "2026-06-10T00:00:00Z",
            "source": "github", "severity": "high", "kind": "bug",
            "title": "outbox finding", "detail": "d",
            "dedupKey": "gh-security:acme/foo", "status": "triage",
        }) + "\n"
        + json.dumps({
            "event": "status", "id": "trg-outbox01",
            "ts": "2026-06-10T00:01:00Z", "newStatus": "snoozed", "by": "cli",
            "reason": "later", "revisitAt": FUTURE,
        }) + "\n",
        encoding="utf-8",
    )
    assert _reimport(tmp_path) is None


def test_one_utc_instant_decides_a_whole_read_across_both_files(
    tmp_path: Path,
) -> None:
    """AC-28. Two entries either side of a UTC midnight, one in each file,
    judged by the same instant — never one against 23:59 and the other 00:00."""
    tracked = _item(tmp_path, dedup_key="k-tracked")
    mark_status(tmp_path, tracked, new_status="snoozed", by="cli",
                reason="later", revisit_at="2026-09-01")
    outbox = tmp_path / ".shipwright" / "triage.outbox.jsonl"
    outbox.write_text(
        json.dumps({
            "event": "append", "id": "trg-outbox02",
            "ts": "2026-06-10T00:00:00Z", "originalTs": "2026-06-10T00:00:00Z",
            "source": "github", "severity": "low", "kind": "bug",
            "title": "t", "detail": "d", "status": "triage",
        }) + "\n"
        + json.dumps({
            "event": "status", "id": "trg-outbox02",
            "ts": "2026-06-10T00:01:00Z", "newStatus": "snoozed", "by": "cli",
            "reason": "later", "revisitAt": "2026-09-02",
        }) + "\n",
        encoding="utf-8",
    )
    at_midnight = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    for stamp in (at_midnight, at_midnight - timedelta(microseconds=1)):
        by_id = {i["id"]: i["status"]
                 for i in read_all_items(tmp_path, now=stamp)}
        # Whatever the instant, both are judged by it consistently.
        assert by_id["trg-outbox02"] == "snoozed"
    assert {i["id"]: i["status"]
            for i in read_all_items(tmp_path, now=at_midnight)}[tracked] \
        == "triage"
    assert {i["id"]: i["status"] for i in read_all_items(
        tmp_path, now=at_midnight - timedelta(microseconds=1))}[tracked] \
        == "snoozed"


def test_read_normalizes_an_aware_non_utc_instant_before_expiry(
    tmp_path: Path,
) -> None:
    item = _item(tmp_path)
    mark_status(tmp_path, item, new_status="snoozed", by="cli",
                reason="later", revisit_at="2026-09-01")
    local_september = datetime(
        2026, 9, 1, 0, 30, tzinfo=timezone(timedelta(hours=14)),
    )
    [resolved] = read_all_items(tmp_path, now=local_september)
    assert resolved["status"] == "snoozed"  # still 2026-08-31 in UTC


def test_read_refuses_a_naive_expiry_instant(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        read_all_items(tmp_path, now=datetime(2026, 9, 1))
