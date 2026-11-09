"""Writer hardening before the events-drop-files flip (S9a precondition): three fixes and one regression pin.

1 a repeated event whose ``ts`` the writer bumped is still recognised as the same event;
2 re-attaching the same commit twice writes one ``event_amended``, not two;
3 an event extra named ``run`` cannot spoof the drop's own run stamp (already safe: pinned, not changed);
4 the F7b seal ships the whole drops and leaves only the torn one behind (it was all-or-nothing); when every
  drop is torn, or the just-written event sits in the torn one, it says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testkit"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_log_probe import event_records  # noqa: E402
from _events_drops_fixtures import _append, _drop_names, _ev, _git, _drops_repo, _layout  # noqa: E402,F401
from tools import commit_event_followup, record_event  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


def test_a_repeated_event_is_not_written_twice_after_the_writer_bumped_its_ts(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000a01"), "r")
    _append(drops_repo, _ev("evt-0000000000000a02"), "r")  # same ts as the first: the writer bumps it by a microsecond
    assert len(event_records(drops_repo)) == 2
    _append(drops_repo, _ev("evt-0000000000000a02"), "r")  # a retry of the second event, original ts
    assert [e["id"] for e in event_records(drops_repo)] == ["evt-0000000000000a01", "evt-0000000000000a02"]


def test_attaching_the_same_commit_twice_records_one_amendment(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000b01", type="work_completed", commit=""), "r")
    assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000b01", "abc1234", "r") is True
    assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000b01", "abc1234", "r") is True
    amendments = [e for e in event_records(drops_repo) if e.get("type") == "event_amended"]
    assert len(amendments) == 1
    assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000b01", "def5678", "r") is True  # a different commit is a new fact
    assert len([e for e in event_records(drops_repo) if e.get("type") == "event_amended"]) == 2


def test_a_run_key_in_the_extras_cannot_spoof_the_drop_run_stamp(drops_repo):
    import tools.finalize_iterate as fin

    extras = {"run": "someone-elses-run", "spec_impact": "none", "spec_impact_reason_code": "docs-only",
              "spec_impact_justification": "docs", "change_type": "docs", "none_reason": "docs"}
    event_id = fin._record_event(drops_repo, "", "iterate-2026-11-07-x", "d", extras)
    assert event_id
    (rec,) = [e for e in event_records(drops_repo) if e.get("id") == event_id]
    assert rec["run"] == "iterate-2026-11-07-x"


def test_the_seal_ships_the_whole_drops_and_reports_the_torn_one(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000c01"), "_main")
    from lib.events_layout import worktree_id
    (drops_repo / "shipwright_events.d" / f"_main--{worktree_id(drops_repo)}--00000002.jsonl").write_text("{torn", encoding="utf-8")
    out = commit_event_followup.commit_followup(drops_repo, "iterate-x")
    assert out["status"] == "committed" and len(out["sealed"]) == 1
    assert out["left_behind"] and "00000002" in out["left_behind"][0]
    tracked = _git(drops_repo, "ls-files", "shipwright_events.d").split()
    assert len(tracked) == 1 and "00000002" not in tracked[0]
    assert len(_drop_names(drops_repo)) == 2  # the torn file stays in the working copy, nothing is deleted


def _torn(root, nonce="00000002", text="{torn"):
    from lib.events_layout import worktree_id
    path = root / "shipwright_events.d" / f"_main--{worktree_id(root)}--{nonce}.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_seal_still_refuses_when_every_pending_drop_is_torn(drops_repo):
    _torn(drops_repo)
    out = commit_event_followup.commit_followup(drops_repo, "iterate-x")
    assert out["status"] == "skipped" and out["reason"] == "invalid_drop"
    assert _git(drops_repo, "ls-files", "shipwright_events.d").strip() == ""


def test_the_seal_says_partial_when_the_just_written_event_sits_in_the_torn_file(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000d01"), "_main")
    _torn(drops_repo, "00000003", '{"v":1,"id":"evt-0000000000000d02","ts":"2026-11-06T10:00:00+00:00","type":"x"}' + chr(10) + '{torn')
    dry = commit_event_followup.commit_followup(drops_repo, "iterate-x", event_id="evt-0000000000000d01", dry_run=True)
    assert dry["status"] == "dry_run" and dry["left_behind"]
    out = commit_event_followup.commit_followup(drops_repo, "iterate-x", event_id="evt-0000000000000d02")
    assert out["status"] == "partial" and out["left_behind"]


def test_attaching_a_commit_again_after_another_one_is_recorded(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000e01", type="work_completed", commit=""), "r")
    for sha in ("abc1234", "def5678", "abc1234"):  # A, B, A: the effective commit must end at A
        assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000e01", sha, "r") is True
    from event_log_probe import effective_records
    (target,) = [e for e in effective_records(drops_repo) if e["id"] == "evt-0000000000000e01"]
    assert target["commit"] == "abc1234"


def test_attach_again_restores_the_commit_after_a_later_non_commit_amendment(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000f01", type="work_completed", commit=""), "r")
    assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000f01", "abc1234", "r") is True
    _append(drops_repo, {"v": 1, "id": "evt-0000000000000f02", "ts": "2026-11-07T10:00:00+00:00", "type": "event_amended",
                         "amends": "evt-0000000000000f01", "fields": {"pr": 12}}, "r")  # readers apply only this one
    from event_log_probe import effective_records
    (target,) = [e for e in effective_records(drops_repo) if e["id"] == "evt-0000000000000f01"]
    assert target["commit"] == ""
    assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000f01", "abc1234", "r") is True
    (target,) = [e for e in effective_records(drops_repo) if e["id"] == "evt-0000000000000f01"]
    assert target["commit"] == "abc1234"


def test_an_unreadable_torn_file_does_not_crash_the_seal(drops_repo, monkeypatch):
    _append(drops_repo, _ev("evt-0000000000000f03"), "_main")
    torn = _torn(drops_repo, "00000009")
    real = commit_event_followup.read_jsonl_records

    def flaky(path, *a, **k):
        if Path(path) == torn:
            raise PermissionError("held open")
        return real(path, *a, **k)
    monkeypatch.setattr(commit_event_followup, "read_jsonl_records", flaky)
    import lib.events_stage as es
    monkeypatch.setattr(es, "read_jsonl_records", flaky)
    out = commit_event_followup.commit_followup(drops_repo, "iterate-x", event_id="evt-0000000000000f04")
    assert out["status"] == "partial"
