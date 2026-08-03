"""The park lifecycle where it meets the store — `triage.py`.

iterate-2026-08-01-triage-defer-lifecycle. The pure rules live in
`test_triage_defer_lifecycle.py`; this file pins what the append-only store
does with them: the revisit date on the wire, expiry in the resolved view, the
transitions that clear it, and the purity of the read. Re-import suppression
has its own file (`test_triage_defer_reimport.py`) — both together were over
the 300-line budget.

Every test that depends on "today" pins it — either by choosing dates far
enough from now that no run can straddle them, or by passing `now` explicitly.
A test that read the real clock would go red on one particular UTC day.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import (  # noqa: E402
    append_triage_item,
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


def _one(project: Path, item_id: str, **kw) -> dict:
    return next(i for i in read_all_items(project, **kw) if i["id"] == item_id)


# ---------------------------------------------------------------------------
# AC-17 / AC-19a — the revisit date on the wire
# ---------------------------------------------------------------------------

def test_a_park_stores_its_revisit_date(tmp_path: Path) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="not now", revisit_at=FUTURE)
    assert _one(tmp_path, item_id)["revisitAt"] == FUTURE


@pytest.mark.parametrize("status", ["triage", "dismissed", "promoted"])
def test_a_revisit_date_is_refused_on_any_status_but_parked(
    tmp_path: Path, status: str,
) -> None:
    """A revisit date IS park semantics. Allowing it elsewhere would let a
    malformed or hostile status event acquire them (external review, round 2)."""
    item_id = _item(tmp_path)
    with pytest.raises(ValueError, match="only on a 'snoozed' flip"):
        mark_status(tmp_path, item_id, new_status=status, by="cli",
                    reason="r", revisit_at=FUTURE)


@pytest.mark.parametrize(
    "bad", ["2026-9-1", "2026-09- 1", "2026-02-30", "2026-09-01T00:00:00Z", " 2026-09-01",
            "soon", ""],
)
def test_a_malformed_revisit_date_is_refused_at_the_store(
    tmp_path: Path, bad: str,
) -> None:
    item_id = _item(tmp_path)
    with pytest.raises(ValueError, match="exact YYYY-MM-DD"):
        mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                    reason="r", revisit_at=bad)


def test_a_refused_revisit_date_writes_nothing(tmp_path: Path) -> None:
    """The validation happens before any I/O, so a rejected call cannot leave
    the entry half-parked."""
    item_id = _item(tmp_path)
    before = (tmp_path / ".shipwright" / "triage.jsonl").read_bytes()
    with pytest.raises(ValueError):
        mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                    reason="r", revisit_at="nope")
    assert (tmp_path / ".shipwright" / "triage.jsonl").read_bytes() == before
    assert _one(tmp_path, item_id)["status"] == "triage"


def test_a_status_line_without_a_park_is_byte_identical_to_before(
    tmp_path: Path,
) -> None:
    """`revisitAt` is OMITTED rather than written null when unset. That is what
    keeps every pre-existing status line — and every committed fixture built
    from one — unchanged by this feature."""
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="dismissed", by="cli", reason="r")
    line = json.loads(
        (tmp_path / ".shipwright" / "triage.jsonl").read_text(
            encoding="utf-8").splitlines()[-1]
    )
    assert "revisitAt" not in line


# ---------------------------------------------------------------------------
# AC-2 / AC-3 — the park expires by itself
# ---------------------------------------------------------------------------

def test_a_park_dated_in_the_future_still_reads_as_parked(
    tmp_path: Path,
) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    assert _one(tmp_path, item_id)["status"] == "snoozed"


def test_a_park_whose_day_has_come_reads_as_open_with_no_second_event(
    tmp_path: Path,
) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=PAST)
    lines_after_park = len(
        (tmp_path / ".shipwright" / "triage.jsonl").read_text(
            encoding="utf-8").splitlines()
    )
    resolved = _one(tmp_path, item_id)
    assert resolved["status"] == "triage"
    assert resolved["revisitDue"] is True
    # Reading did not write. A park expiring is not a decision anybody made.
    assert len(
        (tmp_path / ".shipwright" / "triage.jsonl").read_text(
            encoding="utf-8").splitlines()
    ) == lines_after_park


def test_reading_an_expired_park_leaves_the_stored_event_saying_parked(
    tmp_path: Path,
) -> None:
    """AC-24. The effective status lives only in the resolved view; a replay of
    the raw log must still find `snoozed` as the last word on this entry."""
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=PAST)
    read_all_items(tmp_path)  # the read under test
    raw = [
        json.loads(ln) for ln in
        (tmp_path / ".shipwright" / "triage.jsonl").read_text(
            encoding="utf-8").splitlines()
        if ln.strip()
    ]
    last_status = [r for r in raw if r.get("event") == "status"][-1]
    assert last_status["newStatus"] == "snoozed"


def test_an_expired_park_is_dismissable_again(tmp_path: Path) -> None:
    """`mark_status` compares `expected_status` against the RESOLVED view, so
    an entry that came back on its own behaves like any other open entry."""
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=PAST)
    mark_status(tmp_path, item_id, new_status="dismissed", by="cli",
                reason="handled", expected_status="triage")
    assert _one(tmp_path, item_id)["status"] == "dismissed"


def test_a_park_that_is_not_yet_due_refuses_a_triage_precondition(
    tmp_path: Path,
) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    with pytest.raises(triage.StatusPreconditionError):
        mark_status(tmp_path, item_id, new_status="dismissed", by="cli",
                    reason="x", expected_status="triage")


# ---------------------------------------------------------------------------
# AC-19b/c — a later event clears the date; the two open cases stay apart
# ---------------------------------------------------------------------------

def test_un_parking_clears_the_revisit_date(tmp_path: Path) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    mark_status(tmp_path, item_id, new_status="triage", by="cli",
                reason="parked by mistake")
    resolved = _one(tmp_path, item_id)
    assert (resolved["status"], resolved["revisitAt"]) == ("triage", None)


def test_an_expired_park_and_an_un_parked_entry_are_distinguishable(
    tmp_path: Path,
) -> None:
    """Both read `triage`. The expired one still carries its date; the
    un-parked one does not — which is why no `storedStatus` field is needed."""
    expired = _item(tmp_path, dedup_key="k1")
    unparked = _item(tmp_path, dedup_key="k2")
    mark_status(tmp_path, expired, new_status="snoozed", by="cli",
                reason="later", revisit_at=PAST)
    mark_status(tmp_path, unparked, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    mark_status(tmp_path, unparked, new_status="triage", by="cli", reason="oops")
    assert _one(tmp_path, expired)["revisitAt"] == PAST
    assert _one(tmp_path, unparked)["revisitAt"] is None


def test_re_parking_replaces_the_date(tmp_path: Path) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at="2098-01-01")
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later still", revisit_at=FUTURE)
    assert _one(tmp_path, item_id)["revisitAt"] == FUTURE


# ---------------------------------------------------------------------------
# AC-7 — a damaged or absent date is parked-but-not-due
# ---------------------------------------------------------------------------

def test_a_park_written_without_a_date_stays_parked_forever(
    tmp_path: Path,
) -> None:
    """The Command Center writes exactly this today, and every park written
    before this change has no date. Such an entry must stay visible and
    reversible — never silently re-opened."""
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="webui",
                reason="not now")
    resolved = _one(tmp_path, item_id)
    assert (resolved["status"], resolved["revisitDue"]) == ("snoozed", False)


def test_a_hand_edited_unreadable_date_stays_parked(tmp_path: Path) -> None:
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    store = tmp_path / ".shipwright" / "triage.jsonl"
    store.write_text(
        store.read_text(encoding="utf-8").replace(FUTURE, "whenever"),
        encoding="utf-8",
    )
    assert _one(tmp_path, item_id)["status"] == "snoozed"


@pytest.mark.parametrize("target", ["tracked", "outbox"])
def test_an_unknown_status_event_cannot_rewrite_a_valid_park(
    tmp_path: Path, target: str,
) -> None:
    """The tolerant reader skips a damaged event as a whole; applying only its
    revisitAt would let an unknown status reopen or bury a valid park."""
    item_id = _item(tmp_path)
    mark_status(tmp_path, item_id, new_status="snoozed", by="cli",
                reason="later", revisit_at=FUTURE)
    path = tmp_path / ".shipwright" / (
        "triage.jsonl" if target == "tracked" else "triage.outbox.jsonl"
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "event": "status", "id": item_id, "ts": "2099-12-31T00:00:00Z",
            "newStatus": "hostile", "by": "editor", "reason": "forged",
            "revisitAt": PAST,
        }) + "\n")

    resolved = _one(tmp_path, item_id)
    assert (resolved["status"], resolved["revisitAt"]) == ("snoozed", FUTURE)
    assert (resolved["statusBy"], resolved["statusReason"]) == ("cli", "later")
