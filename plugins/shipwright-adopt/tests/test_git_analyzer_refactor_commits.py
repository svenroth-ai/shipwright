"""git_analyzer.major_refactor_commits — the numstat block must actually be counted.

Root cause of the bug this pins: ``git log --format=... --numstat`` prints a BLANK LINE
between a commit's header and its numstat block::

    <sha>|refactor: restructure modules|<date>|<author>
                                   <-- blank
    12  1   src/a.ts
    9   0   src/b.ts

``analyze_git`` treated that blank as *end of commit*, so it reset ``current = None``
before a single numstat line had been read. ``files_changed`` therefore never rose above
zero, the ``files_changed >= 5`` threshold could never be met, and
``major_refactor_commits`` came back ``[]`` for **every** repository — a permanently dead
field, silently rendering "no major refactors" for a repo full of them.

The blank is a separator, not a terminator: a commit is flushed when the NEXT header
arrives, and the last one by the final flush after the loop.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from git_analyzer import analyze_git  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull, "GIT_AUTHOR_NAME": "T",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "T",
           "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_AUTHOR_DATE": "2024-01-01T12:00:00",
           "GIT_COMMITTER_DATE": "2024-01-01T12:00:00"}
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=False, env=env)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required in CI — install git on the runner")
        pytest.skip("git not available on this machine")
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-gpg-sign", "-m", "chore: seed")
    return root


def _commit_touching(repo: Path, subject: str, files: int, *, tag: str = "a") -> None:
    # `tag` keeps the filenames distinct across commits: identical paths AND identical
    # content would stage nothing, and git would refuse the commit.
    for i in range(files):
        (repo / f"mod_{tag}_{i}.ts").write_text(f"export const {tag}{i} = {i}\n",
                                                encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--no-gpg-sign", "-m", subject)


class TestMajorRefactorCommits:
    def test_a_refactor_touching_many_files_is_detected(self, repo: Path):
        _commit_touching(repo, "refactor: restructure modules", files=6)

        major = analyze_git(repo)["major_refactor_commits"]

        assert len(major) == 1, (
            "the numstat block was not counted — see this module's docstring"
        )
        assert major[0]["subject"] == "refactor: restructure modules"
        assert major[0]["files_changed"] == 6

    def test_a_small_refactor_is_below_the_threshold(self, repo: Path):
        # The signal is a MAJOR refactor: the keyword alone is not enough.
        _commit_touching(repo, "refactor: rename one helper", files=2)
        assert analyze_git(repo)["major_refactor_commits"] == []

    def test_a_large_commit_without_the_keyword_is_not_a_refactor(self, repo: Path):
        _commit_touching(repo, "feat: add six endpoints", files=6)
        assert analyze_git(repo)["major_refactor_commits"] == []

    def test_a_pipe_in_the_subject_does_not_shift_the_other_fields(self, repo: Path):
        # The header used to be "|"-joined, so a subject containing a pipe pushed date
        # and author one field to the right — they came back as fragments of the subject
        # itself. These values are now part of a cross-repo contract AND the sort key, so
        # the format uses 0x1F, which git cannot emit inside %s.
        _commit_touching(repo, "refactor: split a|b parser", files=6)

        commit = analyze_git(repo)["major_refactor_commits"][0]

        assert commit["subject"] == "refactor: split a|b parser"
        assert commit["date"].startswith("2024-01-01")
        assert commit["author"] == "T"

    def test_the_most_recent_refactor_is_still_detected(self, repo: Path):
        # Guards the flush path: the newest commit is the FIRST block in the log and is
        # closed by the next header, while the oldest is closed by the final flush.
        _commit_touching(repo, "refactor: first pass", files=5, tag="one")
        _commit_touching(repo, "chore: unrelated", files=1, tag="two")
        _commit_touching(repo, "refactor: second pass", files=5, tag="three")

        subjects = [c["subject"] for c in analyze_git(repo)["major_refactor_commits"]]
        assert subjects == ["refactor: second pass", "refactor: first pass"]
