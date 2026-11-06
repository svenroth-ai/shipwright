"""Writers and finalization of the drops layout (issue 978, campaign unit S4).

The format changes are DROPS-ONLY: under legacy the bytes stay exactly as before (pinned
here), under the drops layout the run stamp, 16-hex ids, the atomic first write, the closed-file rule,
F6 staging by key, the ensure_current ABSORB step, the F11 committed-check and the F7b seal hold.
Every test sets its layout explicitly, so the standing replay gate (which forces ``drops``) runs them
unchanged: the env override is the test-only one and each test pins what it needs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "testkit"))

from event_log_probe import effective_records, event_files, event_records  # noqa: E402
from lib.events_layout import drop_key, events_layout, worktree_id  # noqa: E402
from lib.events_read import read_events_assembled  # noqa: E402
from lib.events_stage import absorb_wt_drops, own_drops, wt_drops  # noqa: E402
from lib.events_write import new_event_id, write_event_line  # noqa: E402
from tools import record_event  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling fixtures module
from _events_drops_fixtures import _append, _drop_names, _ev, _git, _drops_repo, _layout  # noqa: E402,F401  (_drops_repo: the `drops_repo` fixture)


# --- legacy bytes are unchanged -----------------------------------------------------------------

def test_legacy_bytes_are_exactly_as_before(tmp_path, monkeypatch):
    _layout(monkeypatch, "legacy")
    eid = new_event_id(tmp_path)
    assert re.fullmatch(r"evt-[0-9a-f]{8}", eid)
    event = _ev(eid)
    _append(tmp_path, event, "some-run")
    raw = (tmp_path / "shipwright_events.jsonl").read_bytes()  # Windows text-mode appends CRLF, as ever: compare the line
    assert raw.splitlines() == [json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")]
    assert "run" not in event and not (tmp_path / "shipwright_events.d").exists()


def test_legacy_default_without_any_override_writes_the_legacy_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", raising=False)
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", "drops")  # the plain var changes nothing
    assert events_layout(tmp_path) == "legacy"
    _append(tmp_path, _ev("evt-00000001"))
    assert (tmp_path / "shipwright_events.jsonl").exists() and not (tmp_path / "shipwright_events.d").exists()


def test_ensure_current_absorb_and_seal_are_noops_without_a_drops_folder(drops_repo, monkeypatch):
    _layout(monkeypatch, "legacy")
    _append(drops_repo, _ev("evt-00000002"))
    head = _git(drops_repo, "rev-parse", "HEAD")
    assert absorb_wt_drops(drops_repo, "any-run") is None and wt_drops(drops_repo) == [] and own_drops(drops_repo, "any-run") == []
    assert _git(drops_repo, "rev-parse", "HEAD") == head


# --- the drops writer ---------------------------------------------------------------------------

def test_a_drop_event_is_stamped_has_a_16_hex_id_and_a_validated_name(drops_repo):
    eid = new_event_id(drops_repo)
    assert re.fullmatch(r"evt-[0-9a-f]{16}", eid)
    _append(drops_repo, _ev(eid), "iterate-2026-11-06-x")
    (name,) = _drop_names(drops_repo)
    assert re.fullmatch(r"iterate-2026-11-06-x--[0-9a-f]{8}--[0-9a-f]{8}\.jsonl", name)
    (rec,) = event_records(drops_repo)
    assert rec["run"] == "iterate-2026-11-06-x" and rec["id"] == eid
    assert worktree_id(drops_repo) in name


def test_a_long_run_id_is_capped_at_80_characters_and_stays_a_safe_name(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000003"), "weird run/id:" + "x" * 200)
    (name,) = _drop_names(drops_repo)
    key = name.split("--")[0]
    assert len(key) <= 80 and re.fullmatch(r"[A-Za-z0-9._-]{1,120}", name)
    assert event_records(drops_repo)[0]["run"] == key == drop_key(drops_repo, None, "weird run/id:" + "x" * 200)


def test_key_precedence_explicit_then_branch_then_main(drops_repo, monkeypatch):
    assert drop_key(drops_repo) == "_main"  # the main tree
    assert drop_key(drops_repo, None, "r1") == "r1"  # an explicit id also wins in the main tree
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "from-env")
    assert drop_key(drops_repo) == "from-env" and drop_key(drops_repo, None, "arg") == "arg"
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID")
    wt = drops_repo / ".worktrees" / "wt1"
    _git(drops_repo, "worktree", "add", "-q", "-b", "iterate/some-branch", str(wt))
    assert drop_key(wt) == "_branch-iterate-some-branch"
    unit = drops_repo / ".worktrees" / "campaign-demo--S4"
    _git(drops_repo, "worktree", "add", "-q", "-b", "iterate/u", str(unit))
    assert drop_key(unit) == "campaign-demo--S4"  # the per-unit worktree names itself


def test_a_crash_while_creating_a_drop_leaves_no_file_behind(drops_repo, monkeypatch):
    import lib.events_write as ew

    def boom(*_a, **_k):
        raise OSError("disk full")
    monkeypatch.setattr(ew.os, "replace", boom)
    with pytest.raises(OSError):
        write_event_line(drops_repo, _ev("evt-0000000000000004"), "r")
    folder = drops_repo / "shipwright_events.d"
    assert not folder.exists() or list(folder.iterdir()) == []  # no empty *.jsonl, no stray temp file


def test_the_same_id_with_the_same_content_is_written_once_and_a_different_body_keeps_both(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000005"), "r")
    _append(drops_repo, _ev("evt-0000000000000005"), "r")
    assert len(event_records(drops_repo)) == 1
    _append(drops_repo, _ev("evt-0000000000000005", description="other"), "r")
    read = read_events_assembled(drops_repo)
    assert len(read.records) == 2 and read.duplicate_ids == ["evt-0000000000000005"]


def test_a_closed_file_is_never_edited_the_next_write_rotates(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000006"), "r")
    (first,) = _drop_names(drops_repo)
    _git(drops_repo, "add", "shipwright_events.d")
    _git(drops_repo, "commit", "-q", "-m", "F6")
    committed = (drops_repo / "shipwright_events.d" / first).read_bytes()
    _append(drops_repo, _ev("evt-0000000000000007"), "r")
    names = _drop_names(drops_repo)
    assert len(names) == 2 and (drops_repo / "shipwright_events.d" / first).read_bytes() == committed


def test_attach_commit_becomes_an_event_amended_in_a_new_drop(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000008", type="work_completed", commit=""), "r")
    _git(drops_repo, "add", "shipwright_events.d")
    _git(drops_repo, "commit", "-q", "-m", "F6")
    before = {p.name: p.read_bytes() for p in (drops_repo / "shipwright_events.d").glob("*.jsonl")}
    assert record_event.attach_commit_to_event(drops_repo, "evt-0000000000000008", "abc1234", "r") is True
    assert record_event.attach_commit_to_event(drops_repo, "evt-unknown", "abc1234", "r") is False
    for name, raw in before.items():
        assert (drops_repo / "shipwright_events.d" / name).read_bytes() == raw  # closed file untouched
    (target,) = [e for e in effective_records(drops_repo) if e["id"] == "evt-0000000000000008"]
    assert target["commit"] == "abc1234"
    assert any(e.get("type") == "event_amended" for e in event_records(drops_repo))


# --- readers/validators that carry the stamp -------------------------------------------------------

def test_dedup_event_lines_ignores_the_run_stamp_but_not_other_bytes():
    from lib.churn_merge import dedup_event_lines
    plain = '{"v":1,"id":"evt-1","type":"x"}'
    stamped = '{"v":1,"id":"evt-1","type":"x","run":"r-1"}'
    other = '{"v":1,"id":"evt-1","type":"y","run":"r-1"}'
    out, warnings = dedup_event_lines([plain, stamped, other])
    assert out == [plain, other] and len(warnings) == 1  # same id, distinct body: kept + warned


def test_context_index_hash_ignores_the_run_stamp_and_collapses_fold_duplicates(drops_repo, monkeypatch):
    from lib.event_context_source import iter_event_lines, strip_run
    assert strip_run(b'{"a":1,"run":"r"}\n') == b'{"a":1}\n' and strip_run(b'{"a":1}\n') == b'{"a":1}\n'
    _append(drops_repo, _ev("evt-0000000000000b10"), "run-a")
    folder = drops_repo / "shipwright_events.d"
    (src,) = folder.glob("*.jsonl")
    twin = folder / "run-a--00000000--00000000.jsonl"  # a fold-race twin: same event, stamped differently
    twin.write_text(src.read_text(encoding="utf-8").replace('"run":"run-a"', '"run":"run-z"'), encoding="utf-8")
    assert len(list(iter_event_lines(drops_repo))) == 1


def test_validate_event_log_reads_every_file_and_flags_a_damaged_drop(drops_repo):
    from tools.validate_event_log import validate
    _append(drops_repo, _ev("evt-0000000000000c10"), "run-a")
    assert [i for i in validate(drops_repo) if i["severity"] == "error"] == []
    (path,) = (drops_repo / "shipwright_events.d").glob("*.jsonl")
    path.write_bytes(path.read_bytes() + b"{not json\n")
    errors = [i for i in validate(drops_repo) if i["severity"] == "error"]
    assert errors and any(e.get("file") == path.name for e in errors)


def test_latest_event_dt_survives_an_unconvertible_instant(tmp_path):
    from lib.events_log import latest_event_dt
    (tmp_path / "shipwright_events.jsonl").write_text(
        '{"ts":"0001-01-01T00:00:00+05:00"}\n{"ts":"2026-11-06T10:00:00+00:00"}\n', encoding="utf-8")
    assert latest_event_dt(tmp_path).year == 2026


def test_run_id_resolution_takes_the_newest_run_started_whatever_the_file_order(drops_repo):
    from lib.phase_quality._run_id_resolve import resolve_run_id
    a = _ev("evt-0000000000000d10", type="run_started", run_id="old", ts="2026-11-06T09:00:00+00:00")
    b = _ev("evt-0000000000000d11", type="run_started", run_id="new", ts="2026-11-06T11:00:00+00:00")
    _append(drops_repo, b, "aaa-first-by-name")
    _append(drops_repo, a, "zzz-last-by-name")
    assert resolve_run_id(drops_repo, "sess") == "new"


def test_two_files_are_all_the_drops_a_run_wrote_in_one_worktree(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000e10"), "r")
    assert len(event_files(drops_repo)) == 1 and len(own_drops(drops_repo, "r")) == 1


def _load_seeder():
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-adopt" / "scripts" / "lib" / "event_seeder.py"
    spec = importlib.util.spec_from_file_location("_evt_seeder_s4", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_adopt_seeders_documented_duplicate_matches_the_writer_module(drops_repo):
    seeder = _load_seeder()
    log = drops_repo / "shipwright_events.jsonl"
    seeder.seed_adopted_event(log, profile="p", scope="s", features_inferred=1, nested_excluded=[],
                              plugin_version="1", commit_sha=None)
    seeder.seed_backfill_events(log, [{"sha": "abc", "subject": "x"}])
    (name,) = _drop_names(drops_repo)
    assert re.fullmatch(r"_adopt--[0-9a-f]{8}--[0-9a-f]{8}\.jsonl", name)
    assert name.split("--")[1] == worktree_id(drops_repo)  # wt8 parity with the SSOT
    recs = event_records(drops_repo)
    assert [r["type"] for r in recs] == ["adopted", "work_completed"] and all(r["run"] == "_adopt" for r in recs)
    assert all(re.fullmatch(r"evt-[0-9a-f]{16}", r["id"]) for r in recs) and not log.exists()
    assert seeder.events_target(log).name == name


def test_the_adopt_seeder_still_writes_the_legacy_log_under_legacy(tmp_path, monkeypatch):
    _layout(monkeypatch, "legacy")
    seeder = _load_seeder()
    log = tmp_path / "shipwright_events.jsonl"
    seeder.seed_adopted_event(log, profile="p", scope="s", features_inferred=1, nested_excluded=[],
                              plugin_version="1", commit_sha=None)
    assert log.exists() and not (tmp_path / "shipwright_events.d").exists() and seeder.events_target(log) == log
