"""The release-time fold when something goes wrong: every failure ends in one status, exit 0, and the tree put back.

Companion of ``test_events_fold_for_release.py`` (split to keep both files under the size limit).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _events_fold_release_support import (  # noqa: E402
    OLD, archive_names, commit, drop, ev, events_fold, git, tool, _failing_hook, _hashes, _repo, _run, _tree_state,
)

pytestmark = pytest.mark.covers("FR-01.11")



def test_a_file_that_cannot_be_deleted_is_reported_and_the_tree_is_put_back(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    before = _tree_state(root)
    monkeypatch.setattr(events_fold, "unlink_all", lambda paths: [p.name for p in paths])   # a reader holds them open
    result = _run(root)
    assert result["status"] == "incomplete" and result["not_deleted"] and result["rolled_back"] is True
    assert _tree_state(root) == before


def test_a_half_deleted_fold_is_put_back_too(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    drop(root, "run-old2", ev("e4", OLD))
    commit(root, "second old drop")
    before, events = _tree_state(root), _hashes(root)
    real = events_fold.unlink_all
    monkeypatch.setattr(events_fold, "unlink_all", lambda paths: real(paths[:1]) + [p.name for p in paths[1:]])   # one deleted, one held open
    result = _run(root)
    assert result["status"] == "incomplete" and result["rolled_back"] is True
    assert _tree_state(root) == before and _hashes(root) == events


def test_a_refusing_commit_hook_is_reported_and_the_tree_is_put_back(tmp_path):
    root = _repo(tmp_path)
    _failing_hook(root, tmp_path)
    before = _tree_state(root)
    result = _run(root)
    assert result["status"] == "commit_failed" and result["rolled_back"] is True and "no" in result["reason"]
    assert _tree_state(root) == before, "a hook is never bypassed, and nothing stays behind"


def test_other_staged_work_survives_a_failed_fold(tmp_path):
    root = _repo(tmp_path)
    (root / "other.txt").write_text("release work\n", encoding="utf-8")
    git(root, "add", "other.txt")
    _failing_hook(root, tmp_path)
    assert _run(root)["status"] == "commit_failed"
    assert git(root, "diff", "--cached", "--name-only").split() == ["other.txt"]


def test_an_error_in_the_middle_of_the_fold_puts_the_tree_back(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    before = _tree_state(root)

    def boom(_root):
        raise OSError("disk full")   # after the archive was written and the drop deleted

    monkeypatch.setattr(events_fold, "ensure_keep", boom)
    result = _run(root)
    assert result["status"] == "incomplete" and result["rolled_back"] is True and "disk full" in result["reason"]
    assert _tree_state(root) == before


def test_an_archive_that_does_not_hold_every_event_is_removed_again(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    before = _tree_state(root)
    real = events_fold.durable_atomic_write
    monkeypatch.setattr(events_fold, "durable_atomic_write", lambda path, data: real(path, ""))   # a short write
    result = _run(root)
    assert result["status"] == "incomplete" and result["rolled_back"] is True
    assert _tree_state(root) == before


def test_a_foreign_archive_with_different_content_is_never_deleted(tmp_path):
    root = _repo(tmp_path)
    plan_name = events_fold.plan_fold(root, base_ref="main").archive_name
    foreign = root / "shipwright_events.archive" / plan_name
    foreign.parent.mkdir()
    foreign.write_text("someone else's file" + chr(10), encoding="utf-8")
    result = _run(root)
    assert result["status"] == "skipped" and "rolled_back" not in result
    assert foreign.read_text(encoding="utf-8") == "someone else's file" + chr(10)


def test_a_hook_that_refuses_without_a_word_is_still_a_failed_commit(tmp_path):
    root = _repo(tmp_path)
    _failing_hook(root, tmp_path, "#!/bin/sh" + chr(10) + "exit 1" + chr(10))   # prints nothing
    before = _tree_state(root)
    result = _run(root)
    assert result["status"] == "commit_failed" and result["rolled_back"] is True and "exited with" in result["reason"]
    assert _tree_state(root) == before


def test_a_foreign_untracked_archive_with_the_same_bytes_survives_a_failed_commit(tmp_path):
    root = _repo(tmp_path)
    _failing_hook(root, tmp_path)
    plan = events_fold.plan_fold(root, base_ref="main")
    archive = root / "shipwright_events.archive" / plan.archive_name
    archive.parent.mkdir()
    archive.write_text("".join(json.dumps(r, separators=(",", ":"), ensure_ascii=False) + chr(10) for r in plan.records()), encoding="utf-8", newline=chr(10))
    result = _run(root)
    assert result["status"] == "commit_failed", result
    assert archive.exists(), "a file that was there before the run is never removed"


def test_an_error_before_the_archive_check_never_deletes_a_foreign_archive(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    plan = events_fold.plan_fold(root, base_ref="main")
    archive = root / "shipwright_events.archive" / plan.archive_name
    archive.parent.mkdir()
    archive.write_text("someone else's file" + chr(10), encoding="utf-8", newline=chr(10))

    def boom(*_a, **_k):
        raise OSError("a reader holds the file")

    monkeypatch.setattr(events_fold, "find_conflicts", boom)
    result = _run(root)
    assert result["status"] in ("skipped", "incomplete")
    assert archive.read_text(encoding="utf-8") == "someone else's file" + chr(10)


def test_a_rollback_that_itself_fails_is_reported_not_raised(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _failing_hook(root, tmp_path)
    real = tool._pathspec_git

    def flaky(r, args, paths):
        if args[0] == "reset":
            raise OSError("git is gone")
        return real(r, args, paths)

    monkeypatch.setattr(tool, "_pathspec_git", flaky)
    result = _run(root)
    assert result["status"] == "commit_failed" and result["rolled_back"] is False


def test_the_cli_survives_an_unexpected_error_with_one_json_object_and_exit_zero(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(tool, "fold_for_release", boom)
    assert tool.main(["--project-root", str(root), "--base-ref", "main"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "skipped"


def test_a_commit_that_landed_before_a_failing_later_hook_counts_as_folded(tmp_path):
    root = _repo(tmp_path)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "post-commit").write_text("#!/bin/sh" + chr(10) + "echo late >&2" + chr(10) + "exit 1" + chr(10), encoding="utf-8", newline=chr(10))
    (hooks / "post-commit").chmod(0o755)
    git(root, "config", "core.hooksPath", str(hooks))
    result = _run(root)
    assert result["status"] == "folded" and result["commit"]


def test_a_failed_rollback_keeps_the_archive_because_it_may_be_the_only_copy(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    _failing_hook(root, tmp_path)
    real = tool._pathspec_git

    def flaky(r, args, paths):
        if args[0] == "checkout":
            raise OSError("index.lock")
        return real(r, args, paths)

    monkeypatch.setattr(tool, "_pathspec_git", flaky)
    result = _run(root)
    assert result["status"] == "commit_failed" and result["rolled_back"] is False
    assert archive_names(root), "the events of the deleted drops live in the archive until the drops are back"
