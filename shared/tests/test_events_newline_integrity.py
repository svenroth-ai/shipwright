"""End-to-end newline-integrity of the events append/read boundary.

Sibling of ``test_triage_newline_integrity.py``, for
iterate-2026-07-18-events-jsonl-record-boundary. The leaf-level contract lives in
``test_jsonl_records.py``; this module pins the WIRING — that the real
``record_event`` writers terminate and the real ``config.read_events`` reader
recovers, through the public API.

WHY THIS EXISTS
---------------
PR #399 gave ``triage.py`` a newline guard and record-boundary recovery. It never
considered ``shipwright_events.jsonl``, which is the SAME shape: append-only,
git-tracked, written by many tools across many worktrees, and carrying the SAME
``merge=union`` driver in .gitattributes.

That merge driver is the decisive part. Union merge is line-based: when one side's
blob lacks a trailing newline, git joins its last line to the other side's first
line. So a concatenated record is reachable through an ORDINARY MERGE — no crash,
no interrupted write, no operator edit required. A write-time lock cannot guard
against it, which is why the reader half is load-bearing here even more than it
was for triage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.config import read_events  # noqa: E402
from lib.events_log import resolve_events_path  # noqa: E402
from tools.record_event import append_event  # noqa: E402


def _event(run_id: str, phase: str = "iterate") -> dict:
    return {
        "id": f"evt-{run_id}",
        "type": "work_completed",
        "phase": phase,
        "runId": run_id,
        "ts": "2026-07-18T09:00:00Z",
    }


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# AC1 — the writer terminates, so the next writer cannot concatenate
# ---------------------------------------------------------------------------

def test_append_onto_unterminated_log_does_not_concatenate(tmp_path: Path) -> None:
    """The incident at the writer boundary, mirrored from triage."""
    path = resolve_events_path(tmp_path)
    orphan = {"id": "evt-orphan", "type": "work_completed", "runId": "r-orphan"}
    path.write_bytes(json.dumps(orphan, separators=(",", ":")).encode())  # NO newline

    append_event(tmp_path, _event("r-second"))

    raw = path.read_text(encoding="utf-8")
    assert len(_lines(path)) == 2, raw
    assert raw.endswith("\n")
    for line in _lines(path):
        json.loads(line)  # each physical line parses on its own


def test_append_onto_terminated_log_injects_no_blank_line(tmp_path: Path) -> None:
    path = resolve_events_path(tmp_path)
    path.write_text(
        json.dumps({"id": "evt-a", "type": "work_completed"}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    append_event(tmp_path, _event("r-b"))

    raw = path.read_text(encoding="utf-8")
    assert "\n\n" not in raw
    assert len(_lines(path)) == 2


def test_append_onto_missing_and_empty_log_injects_no_leading_newline(tmp_path: Path) -> None:
    # Missing file.
    append_event(tmp_path, _event("r-fresh"))
    path = resolve_events_path(tmp_path)
    assert not path.read_text(encoding="utf-8").startswith("\n")

    # Zero-byte file — seeking -1 from the end of an empty file must not raise.
    other = tmp_path / "empty-project"
    other.mkdir()
    resolve_events_path(other).write_bytes(b"")
    append_event(other, _event("r-empty"))
    assert not resolve_events_path(other).read_text(encoding="utf-8").startswith("\n")


# ---------------------------------------------------------------------------
# AC2 — the reader recovers, which is what actually guarantees no loss
# ---------------------------------------------------------------------------

def test_read_events_recovers_both_records_from_a_concatenated_line(tmp_path: Path) -> None:
    """The union-merge outcome: two records, one physical line.

    Before the fix ``read_events`` caught JSONDecodeError and skipped the line,
    discarding BOTH events. On an append-only audit trail, corruption must never
    read as absence.
    """
    path = resolve_events_path(tmp_path)
    a = json.dumps(_event("r-a"), separators=(",", ":"))
    b = json.dumps(_event("r-b"), separators=(",", ":"))
    path.write_text(a + b + "\n", encoding="utf-8")  # NO separator between them

    events = read_events(tmp_path)

    assert [e["runId"] for e in events] == ["r-a", "r-b"]


def test_read_events_recovers_partially_and_keeps_the_valid_record(tmp_path: Path) -> None:
    """Partial recovery — all-or-nothing would reproduce the bug it fixes."""
    path = resolve_events_path(tmp_path)
    good = json.dumps(_event("r-good"), separators=(",", ":"))
    path.write_text(good + '{"id":"evt-torn","type":' + "\n", encoding="utf-8")

    events = read_events(tmp_path)

    assert [e["runId"] for e in events] == ["r-good"]


def test_read_events_preserves_wire_order_across_recovered_lines(tmp_path: Path) -> None:
    """Order is load-bearing: last-wins projections depend on it."""
    path = resolve_events_path(tmp_path)
    a = json.dumps(_event("r-1"), separators=(",", ":"))
    b = json.dumps(_event("r-2"), separators=(",", ":"))
    c = json.dumps(_event("r-3"), separators=(",", ":"))
    path.write_text(a + "\n" + b + c + "\n", encoding="utf-8")

    assert [e["runId"] for e in read_events(tmp_path)] == ["r-1", "r-2", "r-3"]


def test_read_events_recovers_the_v1_wire_shape_from_a_concatenated_line(tmp_path: Path) -> None:
    """Same recovery, asserted on the REAL ``v:1`` event shape the tools emit.

    Lives here rather than beside its sibling in
    ``shared/scripts/tools/tests/test_record_event.py``: that file sits at its
    bloat baseline (883 lines) and the anti-ratchet hook refuses growth — "tests
    don't count" is a rationalization it explicitly rejects. This module is the
    regression home for the newline/record-boundary contract anyway.

    Note the warning WORDING changed with this iterate (``<file>:<line>``, the
    post-#399 house format), which is what the one-line assertion update in that
    sibling test pins.
    """
    path = resolve_events_path(tmp_path)
    a = '{"v":1,"id":"evt-good0001","ts":"T","type":"phase_started","phase":"p"}'
    b = '{"v":1,"id":"evt-good0002","ts":"T","type":"phase_completed","phase":"p"}'
    path.write_text(a + b + "\n", encoding="utf-8")

    assert [e["id"] for e in read_events(tmp_path)] == ["evt-good0001", "evt-good0002"]


def test_read_events_still_tolerates_a_wholly_undecodable_line(tmp_path: Path) -> None:
    path = resolve_events_path(tmp_path)
    good = json.dumps(_event("r-ok"), separators=(",", ":"))
    path.write_text("this is not json at all\n" + good + "\n", encoding="utf-8")

    events = read_events(tmp_path)

    assert [e["runId"] for e in events] == ["r-ok"]


def test_read_events_releases_the_file_handle(tmp_path: Path) -> None:
    """Hygiene guard, NOT a regression test — and the distinction is the point.

    The pre-fix reader iterated ``path.open(...)`` with no context manager. I
    expected that to leak a handle and block the unlink on Windows; it did not —
    this test passed BEFORE the fix too, because CPython refcounting closes the
    file object once the for-loop exhausts the generator. So the "leak" is only
    reachable when an exception escapes mid-iteration.

    Kept because ``read_jsonl_records`` uses an explicit context manager and that
    property is worth pinning, but recorded honestly: it does not pin the defect
    this iterate fixed.
    """
    path = resolve_events_path(tmp_path)
    path.write_text(json.dumps(_event("r-x"), separators=(",", ":")) + "\n", encoding="utf-8")

    read_events(tmp_path)

    path.unlink()  # raises PermissionError on Windows if a handle is still open
    assert not path.exists()


# ---------------------------------------------------------------------------
# AC3 — the SECOND, lock-free writer (adopt plugin) terminates too
# ---------------------------------------------------------------------------

def test_adoption_seeder_does_not_concatenate_onto_an_unterminated_log() -> None:
    """`event_seeder` takes no lock and appends repeatedly, so it needs its own
    guard. It cannot import the shared leaf (ADR-045 `sys.modules['lib']`
    collision, verified empirically), so it carries a documented duplicate — this
    pins that the duplicate actually behaves like the SSOT."""
    import importlib.util
    import tempfile

    seeder_path = (
        Path(__file__).resolve().parents[2]
        / "plugins" / "shipwright-adopt" / "scripts" / "lib" / "event_seeder.py"
    )
    spec = importlib.util.spec_from_file_location("_evt_seeder_under_test", seeder_path)
    assert spec and spec.loader
    seeder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seeder)

    with tempfile.TemporaryDirectory() as tmp:
        events = Path(tmp) / "shipwright_events.jsonl"
        events.write_bytes(b'{"id":"evt-orphan","type":"adopted"}')  # NO newline

        seeder._append_jsonl(events, {"id": "evt-new", "type": "adopted"})

        raw = events.read_text(encoding="utf-8")
        assert len(_lines(events)) == 2, raw
        for line in _lines(events):
            json.loads(line)
