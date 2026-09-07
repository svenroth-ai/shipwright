"""Cross-tree discovery edge cases raised by Stage-3 doubt review.

Split out of `test_triage_cross_tree_delivery.py` (which covers the RED-
before-fix scenario and the core discovery/resolution behavior) so that file
stays under 300 lines. See :mod:`lib.triage_cross_tree` for what is under
test and why.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_SCRIPTS = _SHARED / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import triage_cross_tree  # noqa: E402


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _make_main(tmp_path: Path) -> Path:
    """A main tree: `.shipwright/` present, `.git` a DIRECTORY (not a file)."""
    main = tmp_path / "main"
    (main / ".shipwright").mkdir(parents=True)
    (main / ".git").mkdir()
    return main


def _make_worktree(main: Path, slug: str, branch: str) -> Path:
    """A linked worktree under `main/.worktrees/<slug>`: `.git` is a FILE naming
    an admin dir whose `HEAD` names `branch` — the real git worktree shape,
    reproduced without an actual git process."""
    wt = main / ".worktrees" / slug
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / slug
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return wt


_APPEND = {
    "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
    "title": "t", "status": "triage", "severity": "low", "kind": "bug",
    "source": "manual", "detail": "d",
}
_DISMISS = {
    "event": "status", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "newStatus": "dismissed", "by": "cli", "reason": "done",
}


def test_a_relative_gitdir_resolves_against_the_worktree_not_cwd(tmp_path: Path) -> None:
    """git >= 2.48 can write a RELATIVE `gitdir:` target; resolving it against
    the process CWD instead of the worktree's own directory would silently
    disable every sibling at once (Stage-3 doubt review, finding 7)."""
    main = _make_main(tmp_path)
    wt = main / ".worktrees" / "camp-rel"
    admin = main / ".git" / "worktrees" / "camp-rel"
    (wt / ".shipwright").mkdir(parents=True)
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/iterate/camp-rel\n", encoding="utf-8")
    rel = Path("..") / ".." / ".git" / "worktrees" / "camp-rel"
    (wt / ".git").write_text(f"gitdir: {rel}\n", encoding="utf-8")
    (wt / ".shipwright" / "triage.jsonl").write_text(_j({"v": 1}) + "\n", encoding="utf-8")

    found = triage_cross_tree.sibling_worktree_logs(main)
    assert found == [("iterate/camp-rel", wt / ".shipwright" / "triage.jsonl")]


def test_foreign_records_by_branch_drops_append_events(tmp_path: Path) -> None:
    """Only status/amend ever reach a caller — filtered before caching, not
    after (Stage-3 doubt review, finding 1: retaining every foreign append's
    full body is a real memory cost at this repo's measured scale)."""
    main = _make_main(tmp_path)
    wt = _make_worktree(main, "camp-a", "iterate/camp-a")
    (wt / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n", encoding="utf-8")

    [(_branch, records)] = triage_cross_tree.foreign_records_by_branch(main)
    assert [r["event"] for r in records] == ["status"]
