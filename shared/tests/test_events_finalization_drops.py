"""Writers and finalization of the drops layout (issue 978, campaign unit S4).

The format changes are DROPS-ONLY: under legacy the bytes stay exactly as before (pinned
here), under the drops layout the run stamp, 16-hex ids, the atomic first write, the closed-file rule,
F6 staging by key, the ensure_current ABSORB step, the F11 committed-check and the F7b seal hold.
Every test sets its layout explicitly, so the standing replay gate (which forces ``drops``) runs them
unchanged: the env override is the test-only one and each test pins what it needs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import json

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testkit"))

from lib.events_stage import absorb_wt_drops, wt_drops  # noqa: E402
from tools import commit_event_followup, stage_event_drops  # noqa: E402
from tools.verifiers._events_committed import drops_committed_state  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling fixtures module
from _events_drops_fixtures import _append, _drop_names, _ev, _git, _drops_repo, _layout  # noqa: E402,F401  (_drops_repo: the `drops_repo` fixture)


# --- F6 staging, absorb, committed-check, F7b ---------------------------------------------------

def _two_runs(drops_repo: Path) -> None:
    _append(drops_repo, _ev("evt-00000000000000a1"), "run-a")
    _append(drops_repo, _ev("evt-00000000000000b1"), "run-b")


def test_f6_stages_only_this_runs_files_never_the_folder(drops_repo):
    _two_runs(drops_repo)
    result, rc = stage_event_drops.stage(drops_repo, "run-a")
    assert rc == 0 and len(result["staged"]) == 1 and "run-a--" in result["staged"][0]
    staged = _git(drops_repo, "diff", "--cached", "--name-only").split()
    assert staged == result["staged"] and not any("run-b" in s for s in staged)


def test_f6_refuses_a_torn_drop(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000a2"), "run-a")
    (path,) = (drops_repo / "shipwright_events.d").glob("*.jsonl")
    path.write_bytes(path.read_bytes() + b'{"torn":')
    result, rc = stage_event_drops.stage(drops_repo, "run-a")
    assert rc == 1 and result["problems"] and _git(drops_repo, "diff", "--cached", "--name-only") == ""


def test_the_absorb_takes_late_drops_but_leaves_the_run_gate_event_to_f6(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000c1", type="work_completed", adr_id="run-a"), "run-a")  # gate event
    _append(drops_repo, _ev("evt-00000000000000c2"), "late-key")  # a late write of another key
    assert absorb_wt_drops(drops_repo, "run-a") == "events-absorbed"
    tracked = _git(drops_repo, "ls-files", "shipwright_events.d").split()
    assert len(tracked) == 1 and "late-key--" in tracked[0]
    untracked = wt_drops(drops_repo)
    assert len(untracked) == 1 and "run-a--" in untracked[0]  # still F6's job


def test_the_absorb_refuses_a_torn_file_and_commits_nothing(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000d1"), "late-key")
    (path,) = (drops_repo / "shipwright_events.d").glob("*.jsonl")
    path.write_bytes(path.read_bytes() + b"{garbage")
    head = _git(drops_repo, "rev-parse", "HEAD")
    assert absorb_wt_drops(drops_repo, "run-a") == "events-absorb-skipped-invalid"
    assert _git(drops_repo, "rev-parse", "HEAD") == head


def test_f6_forgets_to_stage_then_f11_fails_after_the_absorb_and_passes_once_staged(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000e1", type="work_completed", adr_id="run-e", commit=""), "run-e")
    unsure = drops_committed_state(drops_repo, "", "run-e", None)
    assert unsure is False  # an unstaged drop FAILS the check, it is never None / a pass
    assert absorb_wt_drops(drops_repo, "run-e") is None  # the absorb does not rescue the run's gate event
    assert drops_committed_state(drops_repo, "", "run-e", None) is False
    stage_event_drops.stage(drops_repo, "run-e")
    _git(drops_repo, "commit", "-q", "-m", "F6")
    assert drops_committed_state(drops_repo, "", "run-e", None) is True


def test_an_ignored_drops_folder_does_not_apply_the_committed_assertion(drops_repo):
    (drops_repo / ".gitignore").write_text("*.lock\nshipwright_events.d/\n", encoding="utf-8")
    _append(drops_repo, _ev("evt-00000000000000f1", type="work_completed", adr_id="run-f"), "run-f")
    assert drops_committed_state(drops_repo, "", "run-f", None) is None


def test_legacy_state_stands_when_the_event_is_not_in_a_drop(drops_repo):
    assert drops_committed_state(drops_repo, "", "run-none", True) is True
    assert drops_committed_state(drops_repo, "", "run-none", False) is False


def test_f7b_seals_untracked_main_tree_drops(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000a10"))  # main tree, no explicit run id -> _main
    (name,) = _drop_names(drops_repo)
    assert name.startswith("_main--")
    result = commit_event_followup.commit_followup(drops_repo, "run-x")
    assert result["status"] == "committed" and result["sealed"] == [f"shipwright_events.d/{name}"]
    assert _git(drops_repo, "ls-files", "shipwright_events.d").split() == [f"shipwright_events.d/{name}"]
    assert commit_event_followup.commit_followup(drops_repo, "run-x")["status"] in ("clean", "ignored")


def test_a_merge_that_brings_a_torn_drop_of_the_runs_own_key_is_refused_other_runs_are_tolerated(drops_repo):
    from lib.churn_events import validate_event_folders
    _append(drops_repo, _ev("evt-0000000000000f10"), "run-other")
    _append(drops_repo, _ev("evt-0000000000000f11", type="work_completed", adr_id="run-x"), "run-x")
    assert validate_event_folders(drops_repo, "run-x") == []
    (other,) = (drops_repo / "shipwright_events.d").glob("run-other--*.jsonl")
    other.write_bytes(other.read_bytes() + b"{torn")
    assert validate_event_folders(drops_repo, "run-x") == []  # another run's damage never blocks this run
    _append(drops_repo, _ev("evt-0000000000000f12"), "run-y")
    (mine,) = (drops_repo / "shipwright_events.d").glob("run-y--*.jsonl")
    mine.write_bytes(mine.read_bytes() + b"{torn")
    assert validate_event_folders(drops_repo, "run-y")  # its own damaged drop: "absent" cannot be concluded


def test_convert_configs_writes_through_the_writer_module_under_drops(drops_repo, monkeypatch):
    from tools import convert_configs_to_events as conv
    (drops_repo / "shipwright_build_config.json").write_text(
        json.dumps({"split_01_sections": [{"name": "s1", "commit": "abc"}]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["convert", "--project-root", str(drops_repo)])
    assert conv.main() == 0
    assert not (drops_repo / "shipwright_events.jsonl").exists()
    assert conv.main() == 1  # a second conversion refuses, like the legacy "already exists"


# --- review follow-ups: scope of the absorb, the lock, ordering, line endings -------------------

def test_the_absorb_leaves_an_abandoned_runs_gate_event_alone(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000d1", type="work_completed", adr_id="run-abandoned"), "run-abandoned")
    _append(drops_repo, _ev("evt-00000000000000d2"), "late-key")
    assert absorb_wt_drops(drops_repo, "run-retry") == "events-absorbed"
    assert any("run-abandoned--" in p for p in wt_drops(drops_repo))  # still untracked: its owner's F6 ships it


def test_the_absorb_takes_the_valid_files_when_one_is_torn(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000e1"), "good-key")
    _append(drops_repo, _ev("evt-00000000000000e2"), "bad-key")
    bad = next((drops_repo / "shipwright_events.d").glob("bad-key--*.jsonl"))
    bad.write_bytes(bad.read_bytes() + b'{"torn":')
    assert absorb_wt_drops(drops_repo, "run-x") == "events-absorbed"
    assert [p for p in wt_drops(drops_repo)] == [f"shipwright_events.d/{bad.name}"]


def test_stage_and_absorb_wait_for_the_writers_lock(drops_repo, monkeypatch):
    from lib import events_stage
    seen: list[str] = []

    class _Spy:
        def __init__(self, root):
            seen.append("lock")
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(events_stage, "writer_lock", _Spy)
    monkeypatch.setattr(stage_event_drops, "writer_lock", _Spy)
    _append(drops_repo, _ev("evt-00000000000000f1"), "run-a")
    _append(drops_repo, _ev("evt-00000000000000f2"), "late-key")
    stage_event_drops.stage(drops_repo, "run-a")
    absorb_wt_drops(drops_repo, "run-a")
    assert seen == ["lock", "lock"]


def test_a_coarse_clock_cannot_reorder_one_writers_events_and_drops_stay_lf(drops_repo):
    same = "2026-11-05T10:00:00+00:00"
    _append(drops_repo, _ev("evt-0000000000000a01", ts=same), "run-a")
    _append(drops_repo, _ev("evt-0000000000000a02", ts=same), "run-a")
    (path,) = (drops_repo / "shipwright_events.d").glob("run-a--*.jsonl")
    data = path.read_bytes()
    assert b"\r" not in data
    first, second = (json.loads(x) for x in data.splitlines())
    assert second["ts"] > first["ts"]


def test_a_replayed_event_is_not_written_again_after_its_file_was_closed(drops_repo):
    from lib.events_write import write_event_line
    event = _ev("evt-0000000000000b01", ts="2026-11-05T10:00:00+00:00")
    write_event_line(drops_repo, dict(event), "run-a")
    _git(drops_repo, "add", "-A")
    _git(drops_repo, "commit", "-q", "-m", "close it")
    write_event_line(drops_repo, _ev("evt-0000000000000b02", ts="2026-11-05T11:00:00+00:00"), "run-a")  # a later event, new file
    assert write_event_line(drops_repo, dict(event), "run-a") is None  # the replay is a repeat
    assert len(_drop_names(drops_repo)) == 2


def test_the_run_stamp_is_stripped_only_as_the_last_top_level_member():
    from lib.churn_merge import dedup_event_lines
    a = '{"id":"evt-1","type":"x","detail":{"run":"one"},"run":"k"}\n'
    b = '{"id":"evt-1","type":"x","detail":{"run":"two"},"run":"k"}\n'
    kept, _warn = dedup_event_lines([a, b])
    assert len(kept) == 2  # a nested "run" is content, not routing metadata
    assert len(dedup_event_lines([a, a.replace(',"run":"k"', "")])[0]) == 1
