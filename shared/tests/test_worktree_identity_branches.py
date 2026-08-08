"""Branch-level unit coverage for ``lib.phase_quality._worktree_identity``.

Split out of ``test_pointer_worktree_root_identity.py`` (which covers the
end-to-end redirect behavior via real ``git worktree add`` fixtures) — these
exercise the individual defensive branches (malformed input, unreadable
files, non-UTF-8 content) that a real-git fixture cannot easily reach, and
that this run's diff-coverage gate flagged as unexercised.
"""

from __future__ import annotations

from pathlib import Path

from lib.phase_quality._worktree_identity import (
    fast_main_root,
    is_worktree_of,
    pointer_owned_by_session,
)


def test_fast_main_root_returns_none_on_a_resolve_failure(tmp_path: Path, monkeypatch):
    def boom(self, *args, **kwargs):
        raise OSError("simulated resolve failure")

    monkeypatch.setattr(Path, "resolve", boom)
    assert fast_main_root(tmp_path) is None


def test_fast_main_root_returns_none_when_git_is_not_a_directory(tmp_path: Path):
    (tmp_path / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    assert fast_main_root(tmp_path) is None


def test_pointer_owned_by_session_rejects_a_non_string_session_id(tmp_path: Path):
    """Mirrors pointer_run_id's own structural-spoofing guard: a payload
    whose session_id is e.g. an int must not bind via str()-coercion."""
    assert pointer_owned_by_session({"session_id": 42}, "42") is False


def test_is_worktree_of_rejects_unreadable_git_file(tmp_path: Path):
    """A `.git` FILE whose bytes are not valid UTF-8 must be rejected, not
    raise past the caller."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_bytes(b"\xff\xfe\x00\x01invalid-utf8")
    assert is_worktree_of(worktree.resolve(), tmp_path.resolve()) is False


def test_is_worktree_of_rejects_a_git_file_with_no_gitdir_prefix(tmp_path: Path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("not a gitdir line\n", encoding="utf-8")
    assert is_worktree_of(worktree.resolve(), tmp_path.resolve()) is False


def test_is_worktree_of_rejects_a_gitdir_naming_a_nonexistent_admin_dir(tmp_path: Path):
    """`gitdir.parent == worktrees_root` can hold for a plausible but never-
    created admin dir — `.resolve()` succeeds on a non-strict path, so the
    explicit `is_dir()` check is the only thing that catches it."""
    main_root = tmp_path / "main"
    (main_root / ".git" / "worktrees").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_root / '.git' / 'worktrees' / 'never-created'}\n", encoding="utf-8",
    )
    assert is_worktree_of(worktree.resolve(), main_root.resolve()) is False


def test_is_worktree_of_rejects_an_admin_dir_with_no_back_link_file(tmp_path: Path):
    """A genuine-looking admin dir that is missing git's own `gitdir` back-
    link file (OSError on read) must be rejected, not raise."""
    main_root = tmp_path / "main"
    admin_dir = main_root / ".git" / "worktrees" / "demo"
    admin_dir.mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {admin_dir}\n", encoding="utf-8")
    assert is_worktree_of(worktree.resolve(), main_root.resolve()) is False


def test_is_worktree_of_rejects_a_non_utf8_back_link_file(tmp_path: Path):
    main_root = tmp_path / "main"
    admin_dir = main_root / ".git" / "worktrees" / "demo"
    admin_dir.mkdir(parents=True)
    (admin_dir / "gitdir").write_bytes(b"\xff\xfe\x00\x01invalid-utf8")
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {admin_dir}\n", encoding="utf-8")
    assert is_worktree_of(worktree.resolve(), main_root.resolve()) is False
