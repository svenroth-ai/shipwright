"""The one assembling reader (issue 978, S2): order, per-file status, recovery, duplicates, KC8."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.config import read_events, read_events_result
from lib.events_log import ARCHIVE_DIR, DROPS_DIR
from lib.events_read import EventLogNotReadable, read_events_assembled, require_readable_for_absence

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from _events_read_helpers import _drop, _line, _write  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


def _by_status(read, status):
    return [Path(f.path).name for f in read.files if f.status == status]


def test_no_folders_is_byte_for_byte_the_legacy_read(tmp_path):
    _write(tmp_path / "shipwright_events.jsonl",
           _line(id="b", ts="2026-01-02T00:00:00Z"), _line(id="a", ts="2026-01-01T00:00:00Z"))
    assert [e["id"] for e in read_events(tmp_path)] == ["b", "a"]  # FILE order, not sorted


def test_legacy_first_then_archive_and_drops_by_instant_then_id(tmp_path):
    _write(tmp_path / "shipwright_events.jsonl", _line(id="L2", ts="2026-03-01T00:00:00Z"),
           _line(id="L1", ts="2026-02-01T00:00:00Z"))
    _write(tmp_path / ARCHIVE_DIR / "fold-1.jsonl", _line(id="A", ts="2026-01-15T00:00:00Z"))
    _drop(tmp_path, "run-x", _line(id="D2", ts="2026-01-20T10:00:00+02:00"),  # 08:00Z
          _line(id="D1", ts="2026-01-20T08:00:00Z"))  # same instant, smaller id sorts first
    _drop(tmp_path, "run-y", _line(id="D0", ts="2026-01-10T00:00:00Z"), nonce="00000002")
    assert [e["id"] for e in read_events(tmp_path)] == ["L2", "L1", "D0", "A", "D1", "D2"]


def test_foreign_files_in_the_drops_folder_are_not_read(tmp_path):
    _drop(tmp_path, "run-x", _line(id="D", ts="2026-01-01T00:00:00Z"))
    (tmp_path / DROPS_DIR / "notes.txt").write_text("x")
    (tmp_path / DROPS_DIR / ".lock").write_text("x")
    assert [e["id"] for e in read_events(tmp_path)] == ["D"]


def test_layout_does_not_matter_for_reading(tmp_path, monkeypatch):
    _drop(tmp_path, "run-x", _line(id="D", ts="2026-01-01T00:00:00Z"))
    for value in ("legacy", "drops"):
        monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", value)
        monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
        assert [e["id"] for e in read_events(tmp_path)] == ["D"]


def test_status_ok_corrupt_empty_unreadable(tmp_path, monkeypatch):
    _drop(tmp_path, "r-ok", _line(id="1", ts="2026-01-01T00:00:00Z"))
    _drop(tmp_path, "r-bad", _line(id="2", ts="2026-01-02T00:00:00Z") + "{broken", nonce="00000002")
    _drop(tmp_path, "r-empty", "", nonce="00000003")
    _drop(tmp_path, "r-locked", _line(id="4", ts="2026-01-04T00:00:00Z"), nonce="00000004")
    import lib.events_read as er
    real = er.read_jsonl_records

    def flaky(path, **kw):
        if "r-locked" in str(path):
            raise PermissionError("locked")
        return real(path, **kw)

    monkeypatch.setattr(er, "read_jsonl_records", flaky)
    read = read_events_assembled(tmp_path)
    assert _by_status(read, "ok") == ["r-ok--aaaaaaaa--00000001.jsonl"]
    assert _by_status(read, "corrupt") == ["r-bad--aaaaaaaa--00000002.jsonl"]
    assert _by_status(read, "empty") == ["r-empty--aaaaaaaa--00000003.jsonl"]
    assert _by_status(read, "unreadable") == ["r-locked--aaaaaaaa--00000004.jsonl"]
    assert len(read.skipped_files) == 3
    # recovery: the record in front of the damage is still returned
    assert {e["id"] for e in read.records} == {"1", "2"}
    assert len(read.corrupt) == 1


def test_concatenated_records_on_one_line_are_recovered_in_a_drop(tmp_path):
    a, b = _line(id="a", ts="2026-01-01T00:00:00Z"), _line(id="b", ts="2026-01-02T00:00:00Z")
    _write(tmp_path / DROPS_DIR / "run-c--aaaaaaaa--00000001.jsonl", a + b)
    read = read_events_assembled(tmp_path)
    assert [e["id"] for e in read.records] == ["a", "b"]
    assert [f.status for f in read.files] == ["ok"]


def test_legacy_status_is_listed_only_when_the_file_exists(tmp_path):
    assert read_events_assembled(tmp_path).files == []
    _write(tmp_path / "shipwright_events.jsonl", _line(id="x"))
    only = read_events_assembled(tmp_path).files
    assert [(f.kind, f.status) for f in only] == [("legacy", "ok")]


def test_identical_archive_and_drop_duplicates_collapse_different_content_is_flagged(tmp_path):
    ev = _line(id="same", ts="2026-01-01T00:00:00Z", type="t", n=1)
    _write(tmp_path / ARCHIVE_DIR / "f1.jsonl", ev)
    _write(tmp_path / ARCHIVE_DIR / "f2.jsonl", ev)  # two folds racing: same event twice
    _drop(tmp_path, "run-1", _line(id="clash", ts="2026-01-02T00:00:00Z", n=1))
    _drop(tmp_path, "run-2", _line(id="clash", ts="2026-01-02T00:00:00Z", n=2), nonce="00000002")
    read = read_events_assembled(tmp_path)
    assert [e["id"] for e in read.records].count("same") == 1
    assert [e["id"] for e in read.records].count("clash") == 2
    assert read.duplicate_ids == ["clash"]


def test_legacy_is_never_deduplicated(tmp_path):
    ev = _line(id="dup", ts="2026-01-01T00:00:00Z")
    _write(tmp_path / "shipwright_events.jsonl", ev, ev)
    assert len(read_events(tmp_path)) == 2


def test_kc8_non_ok_drop_of_the_runs_key_blocks_an_absence_gate(tmp_path):
    _drop(tmp_path, "run-mine", _line(id="1", ts="2026-01-01T00:00:00Z") + "{broken")
    read = read_events_result(tmp_path)
    assert [f.status for f in read.absence_blockers("run-mine")] == ["corrupt"]
    with pytest.raises(EventLogNotReadable, match="run-mine"):
        require_readable_for_absence(read, "run-mine")


@pytest.mark.parametrize("status_file", ["empty", "corrupt"])
def test_kc8_other_runs_legacy_and_archive_damage_never_block(tmp_path, status_file):
    broken = "" if status_file == "empty" else "{broken"
    _drop(tmp_path, "run-other", broken)
    _write(tmp_path / ARCHIVE_DIR / "f.jsonl", "{broken")
    _write(tmp_path / "shipwright_events.jsonl", _line(id="ok", ts="2026-01-01T00:00:00Z") + "{broken")
    _drop(tmp_path, "run-mine", _line(id="m", ts="2026-01-02T00:00:00Z"), nonce="00000009")
    read = read_events_result(tmp_path)
    assert read.absence_blockers("run-mine") == []
    require_readable_for_absence(read, "run-mine")  # does not raise
    assert len(read.skipped_files) >= 2  # counted, not hidden


def test_kc8_key_match_is_exact_not_a_prefix(tmp_path):
    _drop(tmp_path, "run-1-extra", "{broken")
    assert read_events_assembled(tmp_path).absence_blockers("run-1") == []


def test_ordering_is_deterministic_for_offsets_ties_and_bad_timestamps(tmp_path):
    """Plan review: equal instants written with different offsets tie and fall to id;
    an unparseable or missing ts sorts first; a conflicting same-id pair stays adjacent."""
    _drop(tmp_path, "run-t",
          _line(id="b", ts="2026-01-01T02:00:00+02:00"),  # == 00:00Z
          _line(id="a", ts="2026-01-01T00:00:00Z"),
          _line(id="bad", ts="not-a-time"),
          _line(id="none"),
          _line(id="z", ts="2026-01-01T00:00:00Z", n=2),
          _line(id="z", ts="2026-01-01T00:00:00Z", n=3))
    read = read_events_assembled(tmp_path)
    assert [e["id"] for e in read.records] == ["bad", "none", "a", "b", "z", "z"]
    assert read.duplicate_ids == ["z"]


def test_a_damaged_drop_keeps_its_key_whatever_the_parse_gave(tmp_path, monkeypatch):
    import lib.events_read as er
    _drop(tmp_path, "run-k", _line(id="1"))

    def boom(path, **kw):
        raise PermissionError("locked")

    monkeypatch.setattr(er, "read_jsonl_records", boom)
    read = read_events_assembled(tmp_path)
    assert [(f.key, f.status) for f in read.absence_blockers("run-k")] == [("run-k", "unreadable")]


def test_kc8_matches_the_key_the_writer_sanitized(tmp_path):
    """Plan review: an 81+ character run id or one with ':' or '/' is renamed by the writer;
    the gate must normalise the same way or it fails open over its own damaged file."""
    from lib.events_layout import sanitize_key
    for run_id in ("r" * 120, "iterate:2026/11/06 odd"):
        _drop(tmp_path, sanitize_key(run_id), "{broken")
        assert len(read_events_assembled(tmp_path).absence_blockers(run_id)) == 1


def test_run_stamp_is_not_content_for_the_duplicate_rule(tmp_path):
    _write(tmp_path / ARCHIVE_DIR / "f.jsonl", _line(id="e", ts="2026-01-01T00:00:00Z", run="fold"))
    _drop(tmp_path, "run-1", _line(id="e", ts="2026-01-01T00:00:00Z", run="run-1"))
    read = read_events_assembled(tmp_path)
    assert len(read.records) == 1 and read.duplicate_ids == []


def test_zero_byte_legacy_is_ok_but_an_empty_drop_is_not(tmp_path):
    (tmp_path / "shipwright_events.jsonl").write_text("")
    _drop(tmp_path, "run-e", "")
    kinds = {f.kind: f.status for f in read_events_assembled(tmp_path).files}
    assert kinds == {"legacy": "ok", "drop": "empty"}


def test_a_drop_deleted_between_listing_and_reading_blocks_absence_of_its_run(tmp_path, monkeypatch):
    """S2 follow-up (b): a vanished drop is recorded non-ok (fail closed), not skipped."""
    import lib.events_read as er
    gone = _drop(tmp_path, "run-g", _line(id="1"))
    real_files = er.event_files
    monkeypatch.setattr(er, "event_files", lambda root: [*real_files(root), gone.with_name("vanished--aaaaaaaa--00000009.jsonl")])
    read = read_events_assembled(tmp_path)
    assert [Path(f.path).name for f in read.files] == [gone.name, "vanished--aaaaaaaa--00000009.jsonl"]
    assert [f.status for f in read.files] == ["ok", "unreadable"]
    assert [f.key for f in read.absence_blockers("vanished")] == ["vanished"]
    assert read.absence_blockers("run-g") == []


def test_a_drop_deleted_between_the_two_exists_checks_is_not_empty(tmp_path, monkeypatch):
    """S2 follow-up (c): ``read_jsonl_records`` maps a missing file to an empty read."""
    import lib.events_read as er
    path = _drop(tmp_path, "run-c", _line(id="1"))
    real = er.read_jsonl_records

    def deleted_first(p, **kw):
        Path(p).unlink()
        return real(p, **kw)

    monkeypatch.setattr(er, "read_jsonl_records", deleted_first)
    read = read_events_assembled(tmp_path)
    assert [(f.status, f.kind) for f in read.files] == [("unreadable", "drop")]
    assert read.absence_blockers("run-c")
    assert not path.exists()


def test_a_legacy_log_deleted_in_between_reads_as_absent_not_empty(tmp_path, monkeypatch):
    import lib.events_read as er
    log = _write(tmp_path / "shipwright_events.jsonl", _line(id="1"))
    real = er.read_jsonl_records

    def deleted_first(p, **kw):
        Path(p).unlink()
        return real(p, **kw)

    monkeypatch.setattr(er, "read_jsonl_records", deleted_first)
    read = read_events_assembled(tmp_path)
    assert read.files == [] and read.records == [] and not log.exists()


def test_instant_survives_an_overflowing_offset():
    """S2 follow-up (a): year-1 plus a positive offset overflows under ``astimezone``."""
    from lib.events_read import instant
    assert instant("0001-01-01T00:00:00+05:00") == instant("garbage")


def test_symlinked_folder_is_not_read(tmp_path):
    real = tmp_path / "elsewhere"
    _write(real / "x--aaaaaaaa--00000001.jsonl", _line(id="1"))
    try:
        (tmp_path / DROPS_DIR).symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert read_events(tmp_path) == []


def test_kc8_a_damaged_drop_with_an_unattributable_name_blocks_every_run(tmp_path):
    _write(tmp_path / DROPS_DIR / "hand-named.jsonl", "{broken")
    assert len(read_events_assembled(tmp_path).absence_blockers("any-run")) == 1


def test_an_unreadable_legacy_log_still_raises_it_never_reads_as_no_events(tmp_path, monkeypatch):
    import lib.events_read as er
    _write(tmp_path / "shipwright_events.jsonl", _line(id="1"))
    real = er.read_jsonl_records

    def locked(path, **kw):
        if Path(path).name == "shipwright_events.jsonl":
            raise PermissionError("locked")
        return real(path, **kw)

    monkeypatch.setattr(er, "read_jsonl_records", locked)
    with pytest.raises(PermissionError):
        read_events_assembled(tmp_path)


def test_a_drop_removed_at_open_time_is_reported_unreadable_never_skipped(tmp_path, monkeypatch):
    import lib.events_read as er
    _drop(tmp_path, "run-v", _line(id="1"))

    def vanished(path, **kw):
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(er, "read_jsonl_records", vanished)
    assert [f.status for f in read_events_assembled(tmp_path).files] == ["unreadable"]


def test_event_lines_at_tolerant_decoding_is_the_callers_choice(tmp_path):
    from lib.events_read import event_lines_at
    log = tmp_path / "shipwright_events.jsonl"
    log.write_bytes(_line(id="a").encode("utf-8") + b'\n{"id":"b","x":"\xff"}\n')
    with pytest.raises(UnicodeDecodeError):
        event_lines_at(log)
    assert len(event_lines_at(log, errors="replace")) == 2


def test_event_context_source_splits_concatenated_records_of_a_drop(tmp_path):
    from lib.event_context_source import iter_event_lines
    _write(tmp_path / "shipwright_events.jsonl", _line(id="a", ts="2026-01-01T00:00:00Z"))
    path = tmp_path / DROPS_DIR / "run-c--aaaaaaaa--00000001.jsonl"
    path.parent.mkdir()
    path.write_text(_line(id="b", ts="2026-01-02T00:00:00Z").strip() + _line(id="c", ts="2026-01-03T00:00:00Z"), encoding="utf-8")
    import json
    assert [json.loads(raw)["id"] for _seq, raw in iter_event_lines(tmp_path)] == ["a", "b", "c"]
