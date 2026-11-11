"""The release-time fold: old merged event files go into the archive in a commit of their own, and never stop a release.

``tools/fold_events_for_release.py`` is called by ``/shipwright-changelog`` before the release's own files are staged.
Real git repos; the base ref is ``main`` (a repo without a remote).
"""


from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _events_fold_release_support import (  # noqa: E402
    NEW, OLD, DROPS_DIR, archive_names, commit, drop, ev, events_fold, git, make_repo, tool, _head_files, _hashes, _repo, _run, _tree_state,
)

pytestmark = pytest.mark.covers("FR-01.11")



def test_old_merged_files_are_folded_in_a_commit_of_their_own(tmp_path):
    root = _repo(tmp_path)
    before, base = _hashes(root), git(root, "rev-parse", "HEAD").strip()
    result = _run(root)
    assert result["status"] == "folded" and result["files"] == 1 and result["events"] == 2
    assert git(root, "rev-parse", "HEAD~1").strip() == base, "exactly one new commit"
    assert git(root, "log", "-1", "--format=%s").startswith("chore(events): fold 1 event files")
    (archive,) = archive_names(root)
    assert _head_files(root) == sorted([f"shipwright_events.archive/{archive}", f"{DROPS_DIR}/run-old--aaaaaaaa--00000001.jsonl",
                                        f"{DROPS_DIR}/.keep"])   # the first fold also adds the empty .keep
    assert (root / DROPS_DIR / "run-new--aaaaaaaa--00000001.jsonl").exists()
    assert _hashes(root) == before, "no event lost or duplicated"
    assert git(root, "status", "--porcelain").strip() == ""


def test_other_staged_work_stays_out_of_the_fold_commit(tmp_path):
    root = _repo(tmp_path)
    (root / "other.txt").write_text("release work\n", encoding="utf-8")
    git(root, "add", "other.txt")
    assert _run(root)["status"] == "folded"
    assert "other.txt" not in _head_files(root)
    assert git(root, "diff", "--cached", "--name-only").split() == ["other.txt"]


def test_an_untracked_file_of_another_run_is_left_alone(tmp_path):
    root = _repo(tmp_path)
    stray = drop(root, "run-live", ev("e9", NEW), nonce="00000007")
    assert _run(root)["status"] == "folded"
    assert stray.exists() and stray.name not in " ".join(_head_files(root))


def test_nothing_old_enough_changes_nothing_and_a_second_run_does_too(tmp_path):
    root = _repo(tmp_path)
    assert _run(root)["status"] == "folded"
    head = git(root, "rev-parse", "HEAD").strip()
    assert _run(root)["status"] == "nothing_to_fold"
    assert git(root, "rev-parse", "HEAD").strip() == head


def test_a_project_on_the_legacy_layout_is_left_alone(tmp_path, monkeypatch):
    for name in ("SHIPWRIGHT_EVENTS_LAYOUT", "SHIPWRIGHT_EVENTS_LAYOUT_TEST"):
        monkeypatch.delenv(name, raising=False)
    root = _repo(tmp_path, layout=None)
    head = git(root, "rev-parse", "HEAD").strip()
    assert _run(root)["status"] == "not_applicable"
    assert git(root, "rev-parse", "HEAD").strip() == head and archive_names(root) == []


def test_a_conflicting_id_skips_the_fold_and_changes_nothing(tmp_path):
    root = _repo(tmp_path)
    drop(root, "run-dup", ev("e1", OLD, description="a different event"))   # same id as e1, other content
    commit(root, "dup")
    head, before = git(root, "rev-parse", "HEAD").strip(), sorted(p.name for p in (root / DROPS_DIR).glob("*.jsonl"))
    result = _run(root)
    assert result["status"] == "skipped" and "different content" in result["reason"]
    assert git(root, "rev-parse", "HEAD").strip() == head and archive_names(root) == []
    assert sorted(p.name for p in (root / DROPS_DIR).glob("*.jsonl")) == before


def test_a_base_ref_that_does_not_resolve_skips_without_error(tmp_path):
    root = _repo(tmp_path)
    result = tool.fold_for_release(str(root), base_ref="origin/main")
    assert result["status"] == "skipped" and "origin/main" in result["reason"]
    assert archive_names(root) == []


@pytest.mark.parametrize("how", ["unstaged", "staged"])
def test_a_file_with_local_changes_is_not_swept_into_the_fold(tmp_path, how):
    """The plan only takes files whose events equal the base's, so the change must be one the plan cannot see:
    a CRLF copy (unstaged, git sees a modification) or a staged edit whose bytes were put back (index differs from HEAD)."""
    root = _repo(tmp_path)
    old = root / DROPS_DIR / "run-old--aaaaaaaa--00000001.jsonl"
    original = old.read_bytes()
    if how == "unstaged":
        old.write_bytes(original.replace(b"\n", b"\r\n"))
    else:
        old.write_bytes(original + b'{"v":1}\n')
        git(root, "add", str(old))
        old.write_bytes(original)
    before = _tree_state(root)
    result = _run(root)
    assert result["status"] == "skipped" and "local changes" in result["reason"]
    assert _tree_state(root) == before


def test_unstaged_release_edits_stay_out_of_the_fold_commit(tmp_path):
    root = _repo(tmp_path)
    (root / "README.md").write_text("edited by the release step\n", encoding="utf-8")
    assert _run(root)["status"] == "folded"
    assert "README.md" not in _head_files(root)
    assert git(root, "status", "--porcelain").strip() == "M README.md"


def test_every_status_reports_how_many_files_are_still_open(tmp_path):
    root = _repo(tmp_path)
    assert _run(root)["open_files"] == 1                  # run-old folded, run-new left
    assert _run(root) == {"status": "nothing_to_fold", "open_files": 1}


def test_a_thousand_files_do_not_overflow_the_command_line(tmp_path):
    root = make_repo(tmp_path)
    (root / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    for i in range(900):
        drop(root, f"run-with-a-fairly-long-key-{i:04d}", ev(f"e{i}", OLD))
    commit(root, "many drops")
    result = _run(root)
    assert result["status"] == "folded" and result["files"] == 900 and len(_head_files(root)) == 901 + 1   # 900 + archive + .keep
    assert git(root, "status", "--porcelain").strip() == ""


def test_the_cli_prints_one_json_object_and_exits_zero(tmp_path, capsys):
    root = _repo(tmp_path)
    assert tool.main(["--project-root", str(root), "--base-ref", "main", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    assert archive_names(root) == []


def test_the_trunk_is_the_one_the_repo_names_when_no_base_ref_is_given(tmp_path):
    root = _repo(tmp_path)
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(root), str(remote))
    git(root, "remote", "add", "origin", str(remote))
    git(root, "fetch", "-q", "origin")
    git(root, "remote", "set-head", "origin", "main")
    result = tool.fold_for_release(str(root))               # no base_ref: origin/HEAD -> origin/main
    assert result["status"] == "folded" and result["files"] == 1


def test_without_any_trunk_the_fold_is_skipped_with_a_reason(tmp_path):
    root = _repo(tmp_path)
    result = tool.fold_for_release(str(root))
    assert result["status"] == "skipped" and "does not resolve" in result["reason"]


def test_every_status_carries_open_files_except_not_applicable(tmp_path, monkeypatch):
    for name in ("SHIPWRIGHT_EVENTS_LAYOUT", "SHIPWRIGHT_EVENTS_LAYOUT_TEST"):
        monkeypatch.delenv(name, raising=False)   # the events replay gate forces drops for the whole run; the legacy repo below must read as legacy
    root = _repo(tmp_path)
    assert "open_files" in tool.fold_for_release(str(root))                           # no trunk: skipped
    assert "open_files" in tool.fold_for_release(str(root), base_ref="main", dry_run=True)
    assert "open_files" not in tool.fold_for_release(str(make_repo(tmp_path, "legacy")))


def test_a_locally_modified_archive_is_not_swept_into_the_fold(tmp_path):
    root = _repo(tmp_path)
    name = events_fold.plan_fold(root, base_ref="main").archive_name
    archive = root / "shipwright_events.archive" / name
    archive.parent.mkdir()
    archive.write_text(json.dumps(ev("zzz-other")) + chr(10), encoding="utf-8", newline=chr(10))
    commit(root, "an archive the fold would also write")
    archive.write_text(json.dumps(ev("zzz-other")) + chr(10) + json.dumps(ev("zzz-edit")) + chr(10), encoding="utf-8", newline=chr(10))
    before = _tree_state(root)
    result = _run(root)
    assert result["status"] == "skipped" and "local changes" in result["reason"]
    assert _tree_state(root) == before


def test_a_staged_rename_of_another_drop_stays_staged_and_out_of_the_fold_commit(tmp_path):
    root = _repo(tmp_path)
    git(root, "mv", str(root / DROPS_DIR / "run-new--aaaaaaaa--00000001.jsonl"), str(root / DROPS_DIR / "run-newer--aaaaaaaa--00000001.jsonl"))
    result = _run(root)
    assert result["status"] == "folded"
    assert not any("run-newer" in f or "run-new--" in f for f in _head_files(root))
    assert git(root, "diff", "--cached", "--name-status").split()[0].startswith("R")


def test_a_project_folder_inside_a_larger_repository_is_skipped(tmp_path):
    root = _repo(tmp_path)
    inner = root / "app"
    inner.mkdir()
    (inner / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    result = tool.fold_for_release(str(inner), base_ref="main")
    assert result["status"] == "skipped" and "top level" in result["reason"]


def test_a_file_that_is_only_on_the_trunk_tip_and_not_at_the_merge_base_is_not_folded(tmp_path):
    """A release branch whose own old drop was squash-merged into the trunk: the integrity check judges against the
    merge-base, so the fold must too (else the archive looks injected)."""
    root = make_repo(tmp_path)
    git(root, "checkout", "-q", "-b", "rel")
    for base in (root,):
        (base / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
        drop(base, "run-old", ev("e1"), ev("e2", OLD))
    commit(root, "the release branch's own drop")
    git(root, "checkout", "-q", "main")
    (root / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    drop(root, "run-old", ev("e1"), ev("e2", OLD))
    commit(root, "the same drop, squash-merged")
    git(root, "checkout", "-q", "rel")
    before = _tree_state(root)
    result = _run(root)                      # base_ref=main: the tip has the file, the merge-base does not
    assert result["status"] == "nothing_to_fold"
    assert _tree_state(root) == before
