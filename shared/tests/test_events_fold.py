"""Fold, emergency fold, full fold, quarantine (issue 978, campaign S6)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`
from _events_fold_helpers import NEW, OLD, archive_names, commit, drop, ev, git, make_repo, put  # noqa: E402
from _events_split import content_key  # noqa: E402

from lib.events_fold import apply_fold, apply_quarantine, plan_fold, plan_quarantine  # noqa: E402
from lib.events_fold_full import apply_full_fold  # noqa: E402
from lib.events_fold_io import event_hash  # noqa: E402
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, QUARANTINE_DIR  # noqa: E402
from lib.events_read import read_events_assembled  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
FOLD_TOOL = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "fold_events.py"
REAL_LOG = Path(__file__).resolve().parents[2] / "shipwright_events.jsonl"


def _hashes(root: Path) -> list[str]:
    return [event_hash(r) for r in read_events_assembled(root).records]


def _repo_with_drops(tmp_path):
    root = make_repo(tmp_path)
    drop(root, "run-old", ev("e1"), ev("e2", OLD))
    drop(root, "run-new", ev("e3", NEW))
    commit(root, "drops")
    return root


def test_fold_moves_only_old_merged_unmodified_drops_into_one_archive(tmp_path):
    root = _repo_with_drops(tmp_path)
    drop(root, "run-local", ev("e4"))                      # old but not committed: not merged
    before = sorted(_hashes(root))
    result = apply_fold(root, plan_fold(root, now=NOW))
    assert result["status"] == "folded" and result["events"] == 2
    assert len(archive_names(root)) == 1 and archive_names(root)[0].startswith("fold-")
    assert sorted(p.name for p in (root / DROPS_DIR).glob("*.jsonl")) == [
        "run-local--aaaaaaaa--00000001.jsonl", "run-new--aaaaaaaa--00000001.jsonl"]
    assert sorted(_hashes(root)) == before                 # the same events, read from archive + drops
    assert (root / DROPS_DIR / ".keep").read_bytes() == b""  # the folder can never be emptied (directory-rename guard)
    reasons = {s["file"]: s["reason"] for s in result["skipped"]}
    assert "newer than" in reasons["run-new--aaaaaaaa--00000001.jsonl"]
    assert "not on the base ref" in reasons["run-local--aaaaaaaa--00000001.jsonl"]


def test_fold_is_idempotent_and_the_archive_name_is_a_function_of_the_set(tmp_path):
    root = _repo_with_drops(tmp_path)
    name = plan_fold(root, now=NOW).archive_name
    apply_fold(root, plan_fold(root, now=NOW))
    assert archive_names(root) == [name]
    again = apply_fold(root, plan_fold(root, now=NOW))
    assert again["status"] == "nothing_to_fold" and archive_names(root) == [name]


def test_a_drop_modified_after_its_commit_is_not_folded(tmp_path):
    root = _repo_with_drops(tmp_path)
    path = root / DROPS_DIR / "run-old--aaaaaaaa--00000001.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(ev("late")) + "\n", encoding="utf-8")
    plan = plan_fold(root, now=NOW)
    reasons = {x["file"]: x["reason"] for x in plan.skipped}
    assert plan.selected == [] and "modified" in reasons[path.name]


def test_corrupt_drops_are_left_unless_asked_and_zero_record_files_are_quarantine_candidates(tmp_path):
    root = make_repo(tmp_path)
    drop(root, "run-bad", ev("g1"), "{broken")
    put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json at all")
    commit(root)
    plan = plan_fold(root, now=NOW)
    assert plan.selected == []
    reasons = " | ".join(s["reason"] for s in plan.skipped)
    assert "include_corrupt" in reasons and "quarantine candidate" in reasons
    assert [s.path.name for s in plan_fold(root, now=NOW, include_corrupt=True).selected] == ["run-bad--aaaaaaaa--00000001.jsonl"]


def test_a_same_id_with_different_content_stops_the_fold(tmp_path):
    root = make_repo(tmp_path)
    put(root, ".", "shipwright_events.jsonl", ev("dup", description="legacy version"))
    drop(root, "run-old", ev("dup", description="drop version"))
    commit(root)
    plan = plan_fold(root, now=NOW)
    assert plan.conflicts == ["dup"]
    refused = apply_fold(root, plan)
    assert refused["status"] == "conflict" and refused["conflicting_ids"] == ["dup"]
    assert not archive_names(root) and list((root / DROPS_DIR).glob("*.jsonl"))
    assert apply_fold(root, plan, allow_conflicts=True)["status"] == "folded"   # keep both, on request


def test_an_identical_copy_elsewhere_is_counted_not_a_conflict(tmp_path):
    root = make_repo(tmp_path)
    put(root, ".", "shipwright_events.jsonl", ev("same"))
    drop(root, "run-old", ev("same"))   # the stamped run is not content
    commit(root)
    plan = plan_fold(root, now=NOW)
    assert plan.conflicts == [] and plan.benign_duplicates == 1


def test_emergency_fold_takes_every_ok_drop_and_flips_the_layout_back(tmp_path):
    root = _repo_with_drops(tmp_path)
    drop(root, "run-local", ev("e4", NEW))
    (root / "shipwright_sync_config.json").write_text(
        json.dumps({"events_layout": "drops", "other": 1}), encoding="utf-8")
    before = sorted(_hashes(root))
    result = apply_fold(root, plan_fold(root, mode="emergency"))
    assert result["status"] == "folded" and result["events"] == 4
    assert not list((root / DROPS_DIR).glob("*.jsonl"))
    cfg = json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8"))
    assert cfg == {"events_layout": "legacy", "other": 1}
    assert sorted(_hashes(root)) == before


def test_full_fold_appends_to_the_legacy_log_dedups_and_leaves_unsafe_files(tmp_path):
    root = make_repo(tmp_path)
    legacy = root / "shipwright_events.jsonl"
    legacy.write_text(json.dumps(ev("l1", NEW)), encoding="utf-8")   # no final newline on purpose
    drop(root, "run-a", ev("l1", NEW), ev("a1"))                     # l1 is already in the legacy log
    put(root, ARCHIVE_DIR, "fold-0123456789ab.jsonl", ev("z1"))
    drop(root, "run-bad", ev("b1"), "{broken", nonce="00000002")
    result = apply_full_fold(root)
    assert result["status"] == "folded_into_legacy" and result["appended"] == 2   # a1, z1; the corrupt file keeps its own b1
    ids = [json.loads(line)["id"] for line in legacy.read_text(encoding="utf-8").splitlines()]
    assert ids.count("l1") == 1 and sorted(ids) == ["a1", "l1", "z1"]
    assert [s["reason"] for s in result["skipped"]] == ["corrupt"]
    assert [p.name for p in (root / DROPS_DIR).glob("*.jsonl")] == ["run-bad--aaaaaaaa--00000002.jsonl"]
    assert not list((root / ARCHIVE_DIR).glob("*.jsonl"))
    assert apply_full_fold(root)["appended"] == 0                                   # idempotent
    assert json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8")) == {"events_layout": "legacy"}


def test_full_fold_refuses_a_conflicting_duplicate_id(tmp_path):
    root = make_repo(tmp_path)
    put(root, ".", "shipwright_events.jsonl", ev("dup", description="a"))
    drop(root, "run-a", ev("dup", description="b"))
    assert apply_full_fold(root)["status"] == "conflict"
    assert (root / DROPS_DIR).exists() and len(list((root / DROPS_DIR).glob("*.jsonl"))) == 1


def test_quarantine_moves_only_zero_record_files_that_were_non_ok_at_the_base(tmp_path):
    root = make_repo(tmp_path)
    junk = put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json at all")
    drop(root, "run-part", ev("p1"), "{broken", nonce="00000002")      # has a recoverable record
    drop(root, "run-fine", ev("f1"), nonce="00000003")
    commit(root)
    raw = junk.read_bytes()
    items = plan_quarantine(root)
    assert [i.path.name for i in items] == ["run-junk--aaaaaaaa--00000001.jsonl"]
    assert apply_quarantine(root, items)["status"] == "quarantined"
    assert (root / QUARANTINE_DIR / junk.name).read_bytes() == raw and not junk.exists()
    assert apply_quarantine(root, plan_quarantine(root))["status"] == "nothing_to_quarantine"


def test_a_file_that_became_junk_after_the_base_is_not_quarantined(tmp_path):
    root = make_repo(tmp_path)
    path = drop(root, "run-fine", ev("f1"))
    commit(root)
    path.write_text("garbage\n", encoding="utf-8")
    assert plan_quarantine(root) == []


@pytest.mark.skipif(not REAL_LOG.exists(), reason="repo log not present")
def test_the_real_log_has_no_conflicting_ids_and_folds_losslessly(tmp_path):
    """Carry-in from S4/S0: scan the REAL log for duplicate ids, and fold its real shape (ids missing, odd ts)."""
    lines = [json.loads(x) for x in REAL_LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    by_id: dict[str, set[str]] = {}
    for rec in lines:
        if isinstance(rec.get("id"), str):
            by_id.setdefault(rec["id"], set()).add(event_hash(rec))
    assert [i for i, hs in by_id.items() if len(hs) > 1] == []          # no conflicting duplicate in the real log
    root = make_repo(tmp_path)
    groups: dict[str, list[str]] = {}
    for rec in lines:   # keys lower-cased: two real run ids differ only in case and would share a file on Windows
        groups.setdefault(content_key(rec).lower(), []).append(json.dumps(rec, separators=(",", ":")))
    for key, group in groups.items():
        put(root, DROPS_DIR, f"{key}--00000000--00000000.jsonl", *group)
    commit(root, "real log, split")
    before = sorted(_hashes(root))
    plan = plan_fold(root, now=datetime(2027, 12, 31, tzinfo=timezone.utc))
    assert plan.conflicts == []
    # the file holding the one undated event is reported, every other file is folded
    assert all("without a ts" in s["reason"] for s in plan.skipped) and len(plan.skipped) == 1
    assert apply_fold(root, plan)["status"] == "folded"
    assert sorted(_hashes(root)) == before
    assert apply_fold(root, plan_fold(root, mode="emergency"))["status"] == "folded"
    assert sorted(_hashes(root)) == before
    assert not list((root / DROPS_DIR).glob("*.jsonl")) and len(before) == len(lines)


def test_cli_dry_run_and_conflict_exit_code(tmp_path):
    root = _repo_with_drops(tmp_path)

    def run(*args):
        return subprocess.run([sys.executable, str(FOLD_TOOL), *args, "--project-root", str(root)],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    assert run("fold", "--dry-run").returncode == 2    # no origin/main here: the merged-ness reference must be named
    dry = run("fold", "--dry-run", "--base-ref", "HEAD")
    assert dry.returncode == 0 and json.loads(dry.stdout)["status"] == "dry_run"
    assert len(list((root / DROPS_DIR).glob("*.jsonl"))) == 2          # nothing moved
    (root / "shipwright_sync_config.json").write_text('{"events_layout": "drops"}', encoding="utf-8")
    commit(root, "layout flag")
    untracked = put(root, DROPS_DIR, "notes.txt", "x")    # anything else in the folder: must NOT be swept in
    done = run("emergency", "--stage")
    assert done.returncode == 0, done.stderr
    status = git(root, "status", "--short").replace("\r", "")
    assert "shipwright_events.archive/fold-" in status and "?? shipwright_events.d/notes.txt" in status
    assert "M  shipwright_sync_config.json" in status           # emergency resets the layout key, staged by name
    untracked.unlink()
    put(root, ".", "shipwright_events.jsonl", ev("x", description="legacy"))
    drop(root, "run-c", ev("x", description="drop"))
    assert run("emergency").returncode == 1                            # refused: conflicting id


def test_emergency_fold_leaves_non_ok_drops_in_place_and_reports_them(tmp_path):
    root = _repo_with_drops(tmp_path)
    put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    result = apply_fold(root, plan_fold(root, mode="emergency"))
    assert [p.name for p in (root / DROPS_DIR).glob("*.jsonl")] == ["run-junk--aaaaaaaa--00000001.jsonl"]
    assert [s["file"] for s in result["skipped"]] == ["run-junk--aaaaaaaa--00000001.jsonl"]


def test_an_interrupted_fold_is_resumable_and_never_loses_an_event(tmp_path, monkeypatch):
    """Crash after the archive is published but before the sources are gone: a re-run finishes the same fold."""
    root = _repo_with_drops(tmp_path)
    before = sorted(_hashes(root))
    real_unlink, calls = Path.unlink, []

    def dying_unlink(self, *a, **kw):
        calls.append(self.name)
        raise OSError("simulated crash")

    monkeypatch.setattr(Path, "unlink", dying_unlink)
    with pytest.raises(OSError):
        apply_fold(root, plan_fold(root, now=NOW))
    monkeypatch.setattr(Path, "unlink", real_unlink)
    assert len(archive_names(root)) == 1 and sorted(set(_hashes(root))) == sorted(set(before))   # visible twice at worst
    again = apply_fold(root, plan_fold(root, now=NOW))
    assert again["status"] == "folded" and archive_names(root) == [again["archive"].split("/")[-1]]
    assert sorted(_hashes(root)) == before and len(archive_names(root)) == 1


def test_emergency_fold_resets_the_layout_even_when_nothing_is_left_to_move(tmp_path):
    root = make_repo(tmp_path)
    (root / "shipwright_sync_config.json").write_text('{"events_layout": "drops"}', encoding="utf-8")
    assert apply_fold(root, plan_fold(root, mode="emergency"))["status"] == "nothing_to_fold"
    assert json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8"))["events_layout"] == "legacy"


def test_quarantine_refuses_a_file_that_gained_a_record_since_the_plan(tmp_path):
    root = make_repo(tmp_path)
    junk = put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    commit(root)
    items = plan_quarantine(root)
    junk.write_text(junk.read_text(encoding="utf-8") + json.dumps(ev("late")) + chr(10), encoding="utf-8")
    assert apply_quarantine(root, items)["status"] == "changed_since_plan"
    assert junk.exists() and not (root / QUARANTINE_DIR).exists()


def test_a_clashing_id_that_appears_after_the_plan_stops_the_fold(tmp_path):
    root = _repo_with_drops(tmp_path)
    plan = plan_fold(root, now=NOW)
    assert plan.conflicts == []
    put(root, ".", "shipwright_events.jsonl", ev("e1", description="a writer got there first"))
    assert apply_fold(root, plan)["status"] == "conflict" and not archive_names(root)


def test_full_fold_never_duplicates_the_events_of_a_file_it_leaves_behind(tmp_path):
    root = make_repo(tmp_path)
    drop(root, "run-bad", ev("b1"), "{broken", nonce="00000002")
    apply_full_fold(root)
    ids = [r["id"] for r in read_events_assembled(root).records]
    assert ids == ["b1"]                                     # from the corrupt drop only, exactly once


def test_quarantine_works_on_a_crlf_checkout(tmp_path):
    root = make_repo(tmp_path)
    junk = put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json", "still not json")
    commit(root)
    junk.write_bytes(junk.read_bytes().replace(bytes([10]), bytes([13, 10])))
    items = plan_quarantine(root)
    assert apply_quarantine(root, items)["status"] == "quarantined"
    assert bytes([13, 10]) not in (root / QUARANTINE_DIR / junk.name).read_bytes()   # the BASE blob is what moves
