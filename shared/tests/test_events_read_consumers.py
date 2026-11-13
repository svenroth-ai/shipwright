"""Consumers of the assembled reader (S2): newest-by-ts pickers, latest_event_dt/finalized_run_ids, KC1 renders."""

from __future__ import annotations

import shutil

import pytest

from lib import events_log
from lib.config import read_events
from lib.event_dedup import last_grade_snapshot
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, finalized_run_ids, latest_event_dt
from lib.events_read import latest_by_ts, read_events_assembled

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))
from _events_read_helpers import FIX, _drop, _line, _split_project, _unsplit_project, _write  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


def _norm(rows: list[dict]) -> list[str]:
    import json
    return [json.dumps(r, sort_keys=True) for r in rows]


def test_latest_by_ts_means_newest_with_the_later_position_on_ties():
    events = [{"id": 1, "ts": "2026-01-03T00:00:00Z"}, {"id": 2, "ts": "2026-01-01T00:00:00Z"},
              {"id": 3, "ts": "2026-01-03T00:00:00Z"}, {"id": 4}]
    assert latest_by_ts(events)["id"] == 3
    assert latest_by_ts(events, lambda e: e["id"] == 2)["id"] == 2
    assert latest_by_ts([]) is None


def test_last_grade_snapshot_is_the_newest_not_the_last_listed():
    def snap(ident, ts):
        return {"type": "grade_snapshot", "id": ident, "ts": ts, "lineage": "main"}

    events = [snap("new", "2026-02-01T00:00:00Z"), snap("old", "2026-01-01T00:00:00Z")]
    assert last_grade_snapshot(events, "main")["id"] == "new"
    assert last_grade_snapshot(events, "branch") is None


def test_latest_event_dt_and_finalized_run_ids_see_drops_and_archive(tmp_path):
    _write(tmp_path / "shipwright_events.jsonl", _line(id="1", ts="2026-01-01T00:00:00Z", adr_id="old"))
    _write(tmp_path / ARCHIVE_DIR / "f.jsonl", _line(id="2", ts="2026-02-01T00:00:00Z", adr_id="arch"))
    _drop(tmp_path, "run-new", _line(id="3", ts="2026-03-01T00:00:00Z", run_id="new"))
    assert latest_event_dt(tmp_path).isoformat() == "2026-03-01T00:00:00+00:00"
    assert finalized_run_ids(tmp_path) == {"old", "arch", "new"}


def test_finalized_run_ids_is_none_when_nothing_exists_or_a_file_is_unreadable(tmp_path, monkeypatch):
    assert finalized_run_ids(tmp_path) is None
    assert latest_event_dt(tmp_path) is None
    _drop(tmp_path, "run-a", _line(id="1", run_id="a"))

    def boom(path, **kw):
        raise PermissionError("locked")

    monkeypatch.setattr(events_log, "read_jsonl_records", boom)
    assert finalized_run_ids(tmp_path) is None
    assert latest_event_dt(tmp_path) is None


def test_empty_drops_folder_alone_reads_as_absent(tmp_path):
    (tmp_path / DROPS_DIR).mkdir(parents=True)
    assert finalized_run_ids(tmp_path) is None
    assert read_events(tmp_path) == []


def test_kc1_readers_agree_on_unsplit_vs_split(tmp_path):
    a, b = _unsplit_project(tmp_path), _split_project(tmp_path)
    assert not (a / DROPS_DIR).exists() and (b / DROPS_DIR).is_dir()
    assert _norm(read_events(a)) == _norm(read_events(b))  # same records, same ORDER
    assert latest_event_dt(a) == latest_event_dt(b)
    assert finalized_run_ids(a) == finalized_run_ids(b)
    assert read_events_assembled(b).skipped_files == []


def test_kc1_renderers_are_byte_identical_on_unsplit_vs_split(tmp_path):
    from tools.generate_session_handoff import generate_handoff
    from tools.iterate_throughput_report import compute_report
    from tools.update_build_dashboard import _generate_from_events

    a, b = _unsplit_project(tmp_path), _split_project(tmp_path)

    def renders(root: Path) -> dict[str, str]:
        return {
            "handoff": generate_handoff(root, session_id="s-fixed", reason="kc1").replace(str(root), "<root>"),
            "dashboard": _generate_from_events(root, session_id="s-fixed", run_id="kc1"),
            "throughput": compute_report(root),
        }

    ra, rb = renders(a), renders(b)
    for name in ra:
        assert ra[name] == rb[name], f"{name} differs between the unsplit baseline and the split log"
        assert ra[name], f"{name} rendered nothing: the comparison would be vacuous"


def test_sorted_by_ts_is_stable_and_newest_last():
    from lib.events_read import sorted_by_ts
    events = [{"id": 1, "ts": "2026-01-03T00:00:00Z"}, {"id": 2, "ts": "2026-01-01T00:00:00Z"},
              {"id": 3, "ts": "2026-01-03T00:00:00Z"}]
    assert [e["id"] for e in sorted_by_ts(events)] == [2, 1, 3]


def test_recent_tables_list_by_ts_when_legacy_holds_a_newer_event_than_a_drop(tmp_path):
    """Mixed layout: a legacy append from an old plugin sorts before the drops in the
    assembled list whatever its ts; the 'newest' tables must still go by ts."""
    from tools.generate_session_handoff import generate_handoff
    from tools.update_build_dashboard import _generate_from_events

    def wc(ident, ts):
        return _line(id=ident, ts=ts, type="work_completed", source="iterate", description=ident,
                     intent="change")
    _write(tmp_path / "shipwright_events.jsonl", wc("legacy-new", "2026-05-01T00:00:00Z"))
    _drop(tmp_path, "run-x", wc("drop-old", "2026-04-01T00:00:00Z"))
    handoff = generate_handoff(tmp_path, session_id="s", reason="r")
    assert handoff.index("legacy-new") < handoff.index("drop-old")  # newest first
    dash = _generate_from_events(tmp_path, session_id="s", run_id="r")
    assert dash.index("legacy-new") < dash.index("drop-old")


def test_grade_snapshot_dedup_treats_a_damaged_file_like_corruption(tmp_path, monkeypatch):
    import types
    from tools import record_event as re_
    seen = {}

    def record_prior(event, prior):
        seen["prior"] = prior
        return None  # never a duplicate: the event is appended

    monkeypatch.setattr(re_, "unchanged_grade_skip", record_prior)
    bad = types.SimpleNamespace(corrupt=[], records=[{"x": 1}], skipped_files=["f"])
    monkeypatch.setattr(re_, "read_events_result", lambda root: bad)
    ev = {"v": 1, "id": "evt-1", "ts": "2026-01-01T00:00:00Z", "type": "grade_snapshot"}
    event_id, skipped = re_.append_event_idempotent(tmp_path, ev, deduplicate_grade_snapshot=True)
    assert seen["prior"] == [] and event_id == "evt-1" and skipped is None


def test_kc1_newest_pickers_agree_when_legacy_is_out_of_ts_order(tmp_path):
    """The shipped fixture is ts-sorted, which makes 'same order' true by construction. Shuffle
    the unsplit log: renders that mean 'newest' must still equal the split render."""
    from tools.generate_session_handoff import generate_handoff
    from tools.update_build_dashboard import _generate_from_events
    lines = (FIX / "unsplit.jsonl").read_text(encoding="utf-8").splitlines()
    shuffled = tmp_path / "shuffled.jsonl"
    shuffled.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8", newline="\n")
    a = tmp_path / "a"
    a.mkdir(parents=True)
    shutil.copyfile(shuffled, a / "shipwright_events.jsonl")
    b = _split_project(tmp_path)
    assert (generate_handoff(a, session_id="s", reason="r").replace(str(a), "<r>")
            == generate_handoff(b, session_id="s", reason="r").replace(str(b), "<r>"))
    assert (_generate_from_events(a, session_id="s", run_id="r")
            == _generate_from_events(b, session_id="s", run_id="r"))


def test_build_history_lists_by_ts_in_a_mixed_layout(tmp_path):
    from tools.update_build_dashboard import _generate_from_events

    def build(ident, ts):
        return _line(id=ident, ts=ts, type="work_completed", source="build", split="default", section=ident,
                     description=ident)
    _write(tmp_path / "shipwright_events.jsonl", build("legacy-new", "2026-05-01T00:00:00Z"))
    _drop(tmp_path, "run-x", build("drop-old", "2026-04-01T00:00:00Z"))
    dash = _generate_from_events(tmp_path, session_id="s", run_id="r")
    assert "drop-old" in dash and "legacy-new" in dash
    assert dash.index("drop-old") < dash.index("legacy-new")  # oldest first
