"""Reading the event log: amendments, record boundaries, unreadable logs (S7).

Split from ``test_fr_change_history_records.py`` (which covers how one record is
interpreted) so neither module crosses the size limit. What lives here is the
layer below interpretation: getting records out of the file at all, and saying
so honestly when that fails.

The theme is one distinction, applied at three depths: "there is nothing here"
must never be confused with "this could not be read". One joined line, one
undecodable fragment, or an entire unopenable file each have their own answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._fr_history_fixtures import SPEC_HEADER, project, work, write_catalog  # noqa: E402

from lib.fr_change_history import (  # noqa: E402
    STATUS_NO_CHANGES,
    change_history_for_fr,
    coverage_summary,
)


# --------------------------------------------------------------------------
# Amendments and record boundaries
# --------------------------------------------------------------------------

def test_an_amendment_that_adds_an_fr_link_is_honoured(tmp_path):
    """26 amendments are live in this repo, and they move the answer."""
    root = project(tmp_path, [
        work(id="evt-1", adr_id="run-a", affected_frs=[]),
        {"type": "event_amended", "amends": "evt-1",
         "fields": {"affected_frs": ["FR-01.01"]}},
    ])
    assert [c.label for c in change_history_for_fr(root, "FR-01.01").changes] == ["run-a"]


def test_an_amendment_that_removes_an_fr_link_is_honoured(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="run-a", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "amends": "evt-1", "fields": {"affected_frs": []}},
    ])
    assert change_history_for_fr(root, "FR-01.01").status == STATUS_NO_CHANGES


def test_the_amendment_record_itself_is_never_reported_as_a_change(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="run-a", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "amends": "evt-1",
         "fields": {"summary": "amended"}, "affected_frs": ["FR-01.01"]},
    ])
    assert len(change_history_for_fr(root, "FR-01.01").changes) == 1


def test_an_amendment_naming_no_target_is_skipped_without_raising(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="run-a", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "fields": {"affected_frs": []}},
    ])
    assert [c.label for c in change_history_for_fr(root, "FR-01.01").changes] == ["run-a"]


def test_two_records_sharing_one_physical_line_are_both_recovered(tmp_path):
    """``merge=union`` is line-based, so a merge can join two records.

    Reading line-at-a-time discards both, turning changes that happened into
    changes that never did.
    """
    root = project(tmp_path, [])
    a = json.dumps(work(id="evt-a", adr_id="run-a", affected_frs=["FR-01.01"]))
    b = json.dumps(work(id="evt-b", adr_id="run-b", affected_frs=["FR-01.01"],
                        ts="2026-02-01T00:00:00+00:00"))
    (root / "shipwright_events.jsonl").write_text(a + b + "\n", encoding="utf-8")
    labels = [c.label for c in change_history_for_fr(root, "FR-01.01").changes]
    assert labels == ["run-a", "run-b"]


def test_a_missing_event_log_yields_no_changes_rather_than_raising(tmp_path):
    split = tmp_path / ".shipwright" / "planning" / "01-adopted"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        SPEC_HEADER + "| FR-01.01 | Adopted | N | Must | D. | code | unit (inferred) |\n",
        encoding="utf-8",
    )
    assert change_history_for_fr(tmp_path, "FR-01.01").status == STATUS_NO_CHANGES


def test_non_work_completed_events_are_not_counted_as_changes(tmp_path):
    root = project(tmp_path, [
        {"type": "phase_completed", "id": "evt-p", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "adr_id": "run-phase"},
    ])
    assert change_history_for_fr(root, "FR-01.01").status == STATUS_NO_CHANGES


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------

def test_coverage_counts_linked_and_total_work_events(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="a", affected_frs=["FR-01.01"]),
        work(id="evt-2", adr_id="b", new_frs=["FR-01.02"]),
        work(id="evt-3", adr_id="c", change_type="docs"),
    ])
    coverage = coverage_summary(root)
    assert (coverage.work_events, coverage.fr_linked_events) == (3, 2)
    assert coverage.unlinked_events == 1


def test_an_event_linked_via_both_fields_is_counted_once(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="a", affected_frs=["FR-01.01"], new_frs=["FR-01.02"]),
    ])
    assert coverage_summary(root).fr_linked_events == 1


def test_coverage_of_an_absent_log_is_zero_not_a_crash(tmp_path):
    assert coverage_summary(tmp_path).work_events == 0


def test_a_history_carries_the_coverage_of_its_own_read(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", adr_id="a", affected_frs=["FR-01.01"]),
        work(id="evt-2", adr_id="b", change_type="docs"),
    ])
    history = change_history_for_fr(root, "FR-01.01")
    assert history.coverage is not None
    assert (history.coverage.work_events, history.coverage.fr_linked_events) == (2, 1)


def test_the_log_is_read_exactly_once_per_query(tmp_path, monkeypatch):
    """The append-only landmine, pinned.

    The log grows while it is read. If the history and the coverage figure
    beside it came from two reads, the pair could describe a state the log was
    never in. Counting the reads is the only way to assert that structurally —
    comparing values would pass by luck on a quiet log.
    """
    import lib._fr_history_events as events_mod
    import lib.fr_change_history as mod

    calls = []
    real = events_mod.read_work_events

    def counting(project_root):
        calls.append(project_root)
        return real(project_root)

    monkeypatch.setattr(mod, "read_work_events", counting)

    root = project(tmp_path, [
        work(id="evt-1", adr_id="a", affected_frs=["FR-01.01"]),
        work(id="evt-2", adr_id="b", change_type="docs"),
    ])
    history = change_history_for_fr(root, "FR-01.01")
    assert len(calls) == 1, f"the event log was read {len(calls)} times, expected 1"
    assert history.coverage.work_events == 2


# --------------------------------------------------------------------------
# An unreadable log is not an empty one
# --------------------------------------------------------------------------

def test_an_unreadable_log_raises_rather_than_answering_empty(tmp_path):
    """"Could not read the log" must not render as "nothing touched this".

    The fragment counting removed that conflation for ONE record; this removes
    it for the whole file, which is the more dangerous case because it hides
    everything rather than one row.
    """
    from lib._fr_history_events import EventLogUnreadable

    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    log = root / "shipwright_events.jsonl"
    log.unlink()
    log.mkdir()  # a directory where a file is expected -> OSError on read

    with pytest.raises(EventLogUnreadable):
        change_history_for_fr(root, "FR-01.01")


def test_undecodable_bytes_surface_as_a_fragment_not_an_exception(tmp_path):
    """The REAL behaviour, replacing a test that passed by never raising.

    External review predicted a ``UnicodeDecodeError`` escaping as a raw
    traceback, reasoning from the type hierarchy (it is a ``ValueError``, so an
    ``OSError`` arm misses it). Probed: ``read_jsonl_records`` opens with
    ``errors="surrogateescape"``, so invalid UTF-8 never raises — it degrades to
    a counted ``corrupt`` fragment, which is exactly the "not silently empty"
    property that mattered. The handler written for it was unreachable and has
    been removed; this asserts what actually happens so the claim is not
    re-derived from types again.
    """
    root = project(tmp_path, [])
    (root / "shipwright_events.jsonl").write_bytes(bytes([0xff, 0xfe, 0x00, 0x00, 0x20, 0xc3, 0x28, 0x0a]))

    history = change_history_for_fr(root, "FR-01.01")
    assert history.status == STATUS_NO_CHANGES
    assert history.corrupt_fragments >= 1, (
        "undecodable bytes vanished silently — the answer would read as "
        "'nothing touched this requirement' over a log that could not be parsed"
    )


def test_a_missing_log_is_still_an_ordinary_empty_answer(tmp_path):
    """CONTROL: absent is NOT unreadable. A fresh project must not raise."""
    write_catalog(tmp_path)
    assert change_history_for_fr(tmp_path, "FR-01.01").status == STATUS_NO_CHANGES


def test_coverage_summary_propagates_the_unreadable_error_too(tmp_path):
    """Both entry points share the reader, so neither may swallow it."""
    from lib._fr_history_events import EventLogUnreadable

    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    log = root / "shipwright_events.jsonl"
    log.unlink()
    log.mkdir()

    with pytest.raises(EventLogUnreadable):
        coverage_summary(root)


def test_an_unimportable_gate_collector_degrades_to_unverifiable(tmp_path, monkeypatch):
    """The documented fallback: a collector that cannot import must not take
    the whole query down.

    ``_collect_known`` catches the import failure and returns a stub reporting
    "no specs found", which routes to ``existence_verified=False`` — the same
    graduated outcome as an unreadable catalog. Asserted rather than assumed:
    it is the one branch that decides whether a broken dependency degrades or
    crashes.
    """
    import sys

    import lib.fr_change_history as mod

    # A module object without the expected attribute makes `from lib.fr_gates
    # import collect_known_fr_ids` raise ImportError, which is what the
    # fallback exists to absorb.
    monkeypatch.setitem(sys.modules, "lib.fr_gates", object())

    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    collector = mod._collect_known()
    assert collector(root) == (frozenset(), False)

    history = mod.change_history_for_fr(root, "FR-01.01")
    assert history.existence_verified is False
    assert history.in_catalog is True, (
        "with nothing to check against, 'not in the catalog' would be a guess"
    )
    assert [c.label for c in history.changes] == ["run-a"], (
        "the query still answers from the log; only existence is unverifiable"
    )
