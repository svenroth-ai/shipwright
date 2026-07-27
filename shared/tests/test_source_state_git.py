"""``source_state.resolve_git_state`` — what the code version actually was.

Card ``trg-4d5b6a56`` (FR-01.10). This is the half of the stamp that is resolved by
CODE rather than declared by the caller: the HEAD commit the tests ran against, and
whether tracked files were modified. Exercised against a REAL git repo, not a mock,
including every way git can be unavailable — because "degrades honestly" is a claim
about real subprocess failures.

Covers ``source_state_git.py``, split from ``source_state.py`` along the same seam.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import subprocess  # noqa: E402

from source_state_git import resolve_git_state  # noqa: E402

RUN = "iterate-2026-07-27-artifact-state-stamping"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one commit — resolution is tested against git, not a mock."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True, text=True, timeout=30)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "tracked.txt"], tmp_path)
    _git(["commit", "-qm", "initial"], tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# AC2 / AC7 — git resolution, including every way git can be unavailable
# --------------------------------------------------------------------------


class TestGitResolution:
    def test_clean_repo_resolves_head_and_not_dirty(self, repo: Path):
        state = resolve_git_state(repo, run_id=RUN)
        assert state.run_id == RUN
        assert state.commit is not None and len(state.commit) == 40
        assert state.dirty is False

    def test_tracked_modification_is_dirty(self, repo: Path):
        (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
        assert resolve_git_state(repo).dirty is True

    def test_untracked_file_alone_is_not_dirty(self, repo: Path):
        # A scratch file does not change which code the tests ran against.
        (repo / "scratch.log").write_text("noise\n", encoding="utf-8")
        assert resolve_git_state(repo).dirty is False

    def test_the_stamped_artifact_itself_does_not_make_the_tree_dirty(self, repo: Path):
        # The reason this exclusion exists: the stamp runs AFTER the record is
        # written, so without it `dirty` would be True on every single run and
        # the field would carry no information at all.
        results = repo / "shipwright_test_results.json"
        results.write_text("{}\n", encoding="utf-8")
        _git(["add", "shipwright_test_results.json"], repo)
        _git(["commit", "-qm", "add results"], repo)
        results.write_text('{"unit": {"total": 1}}\n', encoding="utf-8")
        assert resolve_git_state(repo).dirty is True
        assert resolve_git_state(
            repo, exclude_paths=("shipwright_test_results.json",)
        ).dirty is False

    def test_excluding_the_artifact_still_sees_a_real_source_change(self, repo: Path):
        (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
        state = resolve_git_state(repo, exclude_paths=("shipwright_test_results.json",))
        assert state.dirty is True

    def test_non_repo_degrades_to_none_and_keeps_the_run_id(self, tmp_path: Path):
        state = resolve_git_state(tmp_path, run_id=RUN)
        assert state.commit is None
        assert state.dirty is None
        assert state.run_id == RUN

    def test_empty_repo_with_no_head_degrades(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                       check=True, capture_output=True, text=True, timeout=30)
        state = resolve_git_state(tmp_path, run_id=RUN)
        assert state.commit is None
        assert state.run_id == RUN

    def test_missing_git_binary_does_not_raise(self, repo: Path, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError("git")
        monkeypatch.setattr(subprocess, "run", boom)
        state = resolve_git_state(repo, run_id=RUN)
        assert (state.commit, state.dirty, state.run_id) == (None, None, RUN)

    def test_git_timeout_does_not_raise(self, repo: Path, monkeypatch):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)
        monkeypatch.setattr(subprocess, "run", boom)
        assert resolve_git_state(repo).commit is None

    def test_git_is_never_invoked_through_a_shell(self, repo: Path, monkeypatch):
        seen: list[dict] = []
        real = subprocess.run

        def spy(*a, **k):
            seen.append(k)
            return real(*a, **k)
        monkeypatch.setattr(subprocess, "run", spy)
        resolve_git_state(repo)
        assert seen, "expected at least one git invocation"
        for kwargs in seen:
            assert kwargs.get("shell", False) is False
            assert kwargs.get("timeout") is not None

    def test_an_unusable_run_id_is_dropped_at_resolution(self, repo: Path):
        assert resolve_git_state(repo, run_id="bad\nvalue").run_id is None


