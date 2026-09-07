"""Error paths and cache-hit branches in :mod:`lib.triage_cross_tree` and the
two functions of :mod:`lib.triage_delivery` it drives — split out because
`test_triage_cross_tree_delivery.py` and its discovery-edge-cases sibling
already sit near the 300-line guideline. Every case here corresponds to a
line the diff-coverage gate flagged as unexercised after the Stage-3 doubt
review round: a real `OSError` path, a cache-hit branch never reached because
every prior test's second call also changed `.worktrees`' own mtime, and the
whole-function bodies of `cross_tree_delivery_facts` and
`format_pending_delivery_notice`, which no prior test called directly (only
through the CLI subprocess round-trip, invisible to diff-coverage)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
_SCRIPTS = _SHARED / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402
from lib import triage_cross_tree  # noqa: E402
from lib.triage_delivery import (  # noqa: E402
    foreign_undelivered_from_records,
    format_pending_delivery_notice,
)


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _make_main(tmp_path: Path) -> Path:
    main = tmp_path / "main"
    (main / ".shipwright").mkdir(parents=True)
    (main / ".git").mkdir()
    return main


_APPEND = {
    "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
    "title": "t", "status": "triage", "severity": "low", "kind": "bug",
    "source": "manual", "detail": "d",
}
_DISMISS = {
    "event": "status", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "newStatus": "dismissed", "by": "cli", "reason": "done",
}
_AMEND = {
    "event": "amend", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "by": "cli", "title": "corrected",
}


# ---------------------------------------------------------------------------
# _branch_name — every unreadable/malformed shape skips, never crashes
# ---------------------------------------------------------------------------

def test_branch_name_skips_a_worktree_whose_git_file_is_actually_a_directory(
    tmp_path: Path,
) -> None:
    """`.git` unreadable as text (here: a directory, not a file) must hit the
    `except OSError` path in `_branch_name`, not raise."""
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")
    (wt / ".git").mkdir()  # malformed: a linked worktree's .git must be a FILE

    assert triage_cross_tree.sibling_worktree_logs(main) == []


def test_branch_name_skips_a_git_file_with_no_gitdir_line(tmp_path: Path) -> None:
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")
    (wt / ".git").write_text("not a gitdir line\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == []


def test_branch_name_skips_an_admin_dir_with_no_head_file(tmp_path: Path) -> None:
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")
    admin = main / ".git" / "worktrees" / "camp-a"
    admin.mkdir(parents=True)  # HEAD deliberately absent
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == []


# ---------------------------------------------------------------------------
# sibling_worktree_logs — the not-a-directory guard and the cache-hit branch
# ---------------------------------------------------------------------------

def test_sibling_worktree_logs_empty_when_worktrees_path_is_a_file(tmp_path: Path) -> None:
    """`.worktrees` existing as a plain file (not a directory) must not crash
    `iterdir()` — `base.stat()` succeeds, so the `is_dir()` guard is what
    saves it."""
    main = _make_main(tmp_path)
    (main / ".worktrees").write_text("not a directory\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == []


def test_sibling_worktree_logs_two_consecutive_calls_agree(tmp_path: Path) -> None:
    """Back-to-back calls with NO change to `.worktrees` between them must
    still agree — the walk is unconditional now, not memoized."""
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / "camp-a"
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-a\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")

    first = triage_cross_tree.sibling_worktree_logs(main)
    second = triage_cross_tree.sibling_worktree_logs(main)
    assert first == second == [
        ("iterate/camp-a", wt / ".shipwright" / "triage.jsonl"),
    ]


def test_a_sibling_gaining_a_log_after_the_first_scan_is_picked_up(
    tmp_path: Path,
) -> None:
    """PR #684 review: a worktree already present in `.worktrees` at the first
    scan, but with no `triage.jsonl` yet, must not be permanently excluded once
    one is created — creating a file inside an EXISTING subdirectory changes
    that subdirectory's own mtime, never `.worktrees`' own mtime, so a
    discovery cache keyed on the parent alone would miss this forever."""
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    admin = main / ".git" / "worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-a\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == []

    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == [
        ("iterate/camp-a", wt / ".shipwright" / "triage.jsonl"),
    ]


def test_a_sibling_switching_branch_is_picked_up_without_a_worktrees_change(
    tmp_path: Path,
) -> None:
    """PR #684 review: rewriting an EXISTING sibling's admin `HEAD` (the real
    shape of `git -C <worktree> switch <branch>`) changes neither `.worktrees`'
    own mtime nor its listing, so a cached branch name must not stick."""
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / "camp-a"
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-a\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == [
        ("iterate/camp-a", wt / ".shipwright" / "triage.jsonl"),
    ]

    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-a-v2\n", encoding="utf-8")

    assert triage_cross_tree.sibling_worktree_logs(main) == [
        ("iterate/camp-a-v2", wt / ".shipwright" / "triage.jsonl"),
    ]


def test_a_rewrite_with_a_colliding_mtime_still_invalidates_the_parse_cache(
    tmp_path: Path,
) -> None:
    """PR #684 review: `_CACHE` keyed on bare `st_mtime` (a float) can share a
    value across two rapid rewrites on a coarse-mtime filesystem, serving the
    first write's content forever. Forcing an EXACT mtime collision via
    `os.utime` and changing only the byte content (so `st_size` differs)
    proves the `(mtime_ns, size)` fingerprint still invalidates."""
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / "camp-a"
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-a\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    log_path = wt / ".shipwright" / "triage.jsonl"
    log_path.write_text(_j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    stamp = log_path.stat().st_mtime

    [(_branch, first)] = triage_cross_tree.foreign_records_by_branch(main)
    assert [r["event"] for r in first] == []

    log_path.write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n", encoding="utf-8")
    os.utime(log_path, (stamp, stamp))  # force an exact st_mtime collision
    assert log_path.stat().st_mtime == stamp

    [(_branch, second)] = triage_cross_tree.foreign_records_by_branch(main)
    assert [r["event"] for r in second] == ["status"]


# ---------------------------------------------------------------------------
# cross_tree_delivery_facts — the whole-function bodies, never called
# in-process before (only through the CLI subprocess round-trip)
# ---------------------------------------------------------------------------

def test_cross_tree_delivery_facts_empty_with_no_siblings(tmp_path: Path) -> None:
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")

    result = triage_cross_tree.cross_tree_delivery_facts(
        main, applied_statuses=triage.STATUSES, is_valid_amend=lambda _e: True)
    assert result == (set(), set(), {}, {})


def test_cross_tree_delivery_facts_names_status_and_amend_branches(
    tmp_path: Path,
) -> None:
    """No outbox file exists on this fixture main tree — exercising the
    `_cached_records` not-found path for `.shipwright/triage.outbox.jsonl`
    at the same time as the function's normal, populated path."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    wt = main / ".worktrees" / "camp-a"
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / "camp-a"
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-a\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n" + _j(_AMEND) + "\n",
        encoding="utf-8")

    status_ids, amend_ids, status_branches, amend_branches = (
        triage_cross_tree.cross_tree_delivery_facts(
            main, applied_statuses=triage.STATUSES, is_valid_amend=lambda _e: True)
    )
    assert status_ids == {"trg-good0001"}
    assert amend_ids == {"trg-good0001"}
    assert status_branches == {"trg-good0001": "iterate/camp-a"}
    assert amend_branches == {"trg-good0001": "iterate/camp-a"}


# ---------------------------------------------------------------------------
# lib.triage_delivery — the guard clause and the human-notice formatter
# ---------------------------------------------------------------------------

def test_foreign_undelivered_from_records_rejects_an_empty_status_vocabulary() -> None:
    with pytest.raises(ValueError, match="applied_statuses"):
        foreign_undelivered_from_records([], [], [], applied_statuses=set())


def test_format_pending_delivery_notice_labels_known_and_unknown_branches() -> None:
    """One id with a known origin branch, one without — exercises both arms
    of the inner `_label` helper and the default `origin_branches=None`."""
    text = format_pending_delivery_notice({"trg-aaa00001"})
    assert text is not None
    assert "trg-aaa00001" in text

    text2 = format_pending_delivery_notice(
        {"trg-aaa00001", "trg-bbb00002"},
        origin_branches={"trg-bbb00002": "iterate/camp-a"},
    )
    assert text2 is not None
    assert "trg-aaa00001" in text2
    assert "'trg-bbb00002' (on 'iterate/camp-a', not yet merged here)" in text2
