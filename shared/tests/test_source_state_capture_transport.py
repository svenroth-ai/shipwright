"""``source_state_capture`` — HOW the captured answer travels (``trg-f5ae5371``).

The value is carried in ``os.environ`` so that a subprocess inherits it for free,
and it is honoured only when BOTH the run id and the tree match. Both halves are
claims about real processes, so both are exercised with a real subprocess and real
fixture repos rather than with a mock.

The tree binding exists because a run id alone is not enough: one process can carry
a single run id while acting on more than one root, and honouring a capture there
would answer for a tree nobody measured (Stage-3 doubt D1). WHAT the capture answers
is the sibling module ``test_source_state_capture.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from source_state_capture import (  # noqa: E402
    ENV_DIRTY, ENV_DIRTY_ROOT, ENV_DIRTY_RUN, capture_dirty, captured_dirty,
)

RUN = "iterate-2026-08-01-grade-snapshot-dirty-capture"
OTHER_RUN = "iterate-2026-07-31-some-other-run"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", "-C", str(cwd), *args],
                   check=True, capture_output=True, text=True, timeout=30)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one commit and a clean tree."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True, text=True, timeout=30)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    # A developer with commit.gpgsign=true globally would otherwise fail every
    # commit here and error the whole module out rather than test anything.
    _git(["config", "commit.gpgsign", "false"], tmp_path)
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "tracked.txt"], tmp_path)
    _git(["commit", "-qm", "initial"], tmp_path)
    return tmp_path


def _dirty_the_tree(repo: Path) -> None:
    """Modify a TRACKED file — exactly what an automatic producer does."""
    (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")


# --------------------------------------------------------------------------
# AC1 — at most one measurement per run: the first capture wins
# --------------------------------------------------------------------------


class TestRoundTrip:
    def test_capture_is_readable_back(self, repo: Path):
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        assert captured_dirty(RUN, env=env) is False

    def test_true_round_trips_as_true(self, repo: Path):
        _dirty_the_tree(repo)
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        assert captured_dirty(RUN, env=env) is True

    def test_a_different_run_does_not_read_this_capture(self, repo: Path):
        """The run-id binding: a stale export must not be honoured by another run."""
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        assert captured_dirty(OTHER_RUN, env=env) is None

    def test_a_different_run_re_measures_rather_than_inheriting(self, repo: Path):
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)          # clean → False, bound to RUN
        _dirty_the_tree(repo)
        assert capture_dirty(repo, OTHER_RUN, env=env) is True


class TestBoundToATreeAsWellAsARun:
    """A run id alone is not enough (Stage-3 doubt D1).

    One process can legitimately carry a single run id while acting on more than one
    root — a merge helper, a campaign driver, or this repo's own test suite, where
    several modules reuse one run id across per-test fixture repos. Honouring a
    capture there would answer for a tree nobody measured.
    """

    def test_same_run_different_tree_is_re_measured(self, repo: Path, tmp_path: Path):
        second = tmp_path / "second"
        subprocess.run(["git", "init", "-q", "-b", "main", str(second)],
                       check=True, capture_output=True, text=True, timeout=30)
        _git(["config", "user.email", "t@example.com"], second)
        _git(["config", "user.name", "t"], second)
        _git(["config", "commit.gpgsign", "false"], second)
        (second / "tracked.txt").write_text("v1\n", encoding="utf-8")
        _git(["add", "tracked.txt"], second)
        _git(["commit", "-qm", "initial"], second)
        (second / "tracked.txt").write_text("v2\n", encoding="utf-8")  # genuinely dirty

        env: dict[str, str] = {}
        assert capture_dirty(repo, RUN, env=env) is False       # tree A: clean
        # Same run id, different tree — the clean answer must NOT carry over.
        assert capture_dirty(second, RUN, env=env) is True

    def test_each_tree_keeps_its_first_capture_when_the_process_returns_to_it(
        self, repo: Path, tmp_path: Path,
    ):
        """A/B/A regression from external review.

        Capturing B must not erase A's pre-write answer. Otherwise returning to A
        after a producer dirtied it recreates the withdrawn emit-time bug.
        """
        second = tmp_path / "second"
        subprocess.run(["git", "init", "-q", "-b", "main", str(second)],
                       check=True, capture_output=True, text=True, timeout=30)
        _git(["config", "user.email", "t@example.com"], second)
        _git(["config", "user.name", "t"], second)
        _git(["config", "commit.gpgsign", "false"], second)
        (second / "tracked.txt").write_text("v1\n", encoding="utf-8")
        _git(["add", "tracked.txt"], second)
        _git(["commit", "-qm", "initial"], second)

        env: dict[str, str] = {}
        assert capture_dirty(repo, RUN, env=env) is False       # A: clean
        assert capture_dirty(second, RUN, env=env) is False     # B: clean
        _dirty_the_tree(repo)                                   # producer writes A
        assert capture_dirty(repo, RUN, env=env) is False, (
            "tree B erased tree A's pre-write capture")

    def test_same_run_same_tree_still_inherits(self, repo: Path):
        """The guard must not defeat the mechanism it protects."""
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        _dirty_the_tree(repo)
        assert capture_dirty(repo, RUN, env=env) is False

    def test_a_subdirectory_inherits_the_same_worktree_capture(self, repo: Path):
        """Repo root and subdirectory are two paths to the same Git worktree."""
        child = repo / "nested" / "child"
        child.mkdir(parents=True)
        env: dict[str, str] = {}
        assert capture_dirty(repo, RUN, env=env) is False
        _dirty_the_tree(repo)
        assert capture_dirty(child, RUN, env=env) is False, (
            "subdirectory bypassed the worktree's pre-write capture")

    def test_matching_run_without_a_root_is_re_measured(self, repo: Path):
        """An incomplete export is not a wildcard for every tree (external review)."""
        env = {ENV_DIRTY_RUN: RUN, ENV_DIRTY: "0"}
        _dirty_the_tree(repo)
        assert capture_dirty(repo, RUN, env=env) is True
        assert env[ENV_DIRTY_ROOT] == str(repo.resolve())

    def test_the_root_is_recorded(self, repo: Path):
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        assert env[ENV_DIRTY_ROOT] == str(repo.resolve())

    def test_a_reader_naming_another_tree_gets_unknown(self, repo: Path, tmp_path: Path):
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        assert captured_dirty(RUN, tmp_path / "elsewhere", env=env) is None

    def test_a_reader_naming_no_tree_still_reads_the_run(self, repo: Path):
        """Omitting the root asks 'what was recorded for this run' — the answer a
        caller with no tree in hand wants, and the pre-existing behaviour."""
        env: dict[str, str] = {}
        capture_dirty(repo, RUN, env=env)
        assert captured_dirty(RUN, env=env) is False

    def test_child_process_inherits_the_capture(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """The claim the whole transport rests on, exercised as production does it.

        No ``env=`` anywhere: the capture writes the real ``os.environ``, and the
        child is spawned with plain inheritance — which is exactly how
        ``finalize_iterate`` spawns the compliance regen. Handing the child an
        explicit ``env`` dict would prove only that a dict passed in is visible,
        which is trivially true and not the mechanism.
        """
        # Registered so monkeypatch removes what the CODE is about to write.
        for name in (ENV_DIRTY, ENV_DIRTY_RUN, ENV_DIRTY_ROOT):
            monkeypatch.setenv(name, "sentinel")
            monkeypatch.delenv(name, raising=False)

        capture_dirty(repo, RUN)                 # writes real os.environ
        _dirty_the_tree(repo)                    # the producer writes, as it does
        probe = (
            "import sys;"
            f"sys.path.insert(0, {str(_SCRIPTS)!r});"
            "from source_state_capture import capture_dirty;"
            f"print(capture_dirty({str(repo)!r}, {RUN!r}))"
        )
        out = subprocess.run([sys.executable, "-c", probe],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "False", (
            f"child re-measured the dirtied tree instead of inheriting: {out.stdout!r}")

    def test_child_without_the_capture_does_measure(self, repo: Path):
        """The counterweight: with nothing in the environment the same child reports
        the dirtied tree. Without this, the test above could pass for the wrong
        reason — e.g. if the child silently failed to measure at all."""
        _dirty_the_tree(repo)
        probe = (
            "import sys;"
            f"sys.path.insert(0, {str(_SCRIPTS)!r});"
            "from source_state_capture import capture_dirty;"
            f"print(capture_dirty({str(repo)!r}, {RUN!r}))"
        )
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in (ENV_DIRTY, ENV_DIRTY_ROOT, ENV_DIRTY_RUN)}
        out = subprocess.run([sys.executable, "-c", probe], env=clean_env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "True"
