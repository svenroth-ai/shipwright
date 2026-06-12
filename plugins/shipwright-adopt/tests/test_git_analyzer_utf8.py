"""UTF-8 regression tests for adopt git_analyzer (deep-audit WP7 / F23).

`_run_git` decoded subprocess output with `text=True` but no explicit
`encoding=`, so on a Windows dev box git's UTF-8 byte stream was decoded
as cp1252. A Cyrillic / CJK / 0x9D commit subject then raised
`UnicodeDecodeError`, which escaped `_run_git`'s `except` (it only caught
`SubprocessError` / `FileNotFoundError`) and crashed `/shipwright-adopt`.

These tests run the REAL analyzer over a REAL git repo whose commit
subjects contain CJK, Cyrillic, and a raw 0x9D byte (the historical
crasher), asserting no exception escapes and the subjects round-trip.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lib.git_analyzer import _run_git, analyze_git


def _git(cwd: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Тест Author",  # Cyrillic author name
            "GIT_AUTHOR_EMAIL": "t@test.invalid",
            "GIT_COMMITTER_NAME": "Тест Author",
            "GIT_COMMITTER_EMAIL": "t@test.invalid",
        }
    )
    subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                   capture_output=True)


@pytest.fixture
def cjk_git_repo(tmp_path: Path) -> Path:
    """A git repo whose commit subjects carry CJK + Cyrillic + a 0x9D byte.

    git stores the commit message bytes verbatim and emits them as UTF-8 on
    `git log`; the 0x9D byte makes the stream invalid cp1252 (0x9D is
    undefined there) — the exact crasher the audit found.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    # Commit 1 — CJK subject.
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "重构 refactor 配置加载")
    # Commit 2 — Cyrillic subject, > 5 files so it qualifies as "major".
    for i in range(6):
        (repo / f"f{i}.txt").write_text(f"{i}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "рефакторинг migrate большой переезд")
    # Commit 3 — a RAW 0x9D byte in the subject. This must be a bare byte,
    # not the str escape "\x9d": "\x9d".encode("utf-8") yields the valid
    # 2-byte sequence C2 9D (U+009D), which decodes fine and would NOT
    # reproduce the crasher. A lone 0x9D is invalid standalone UTF-8 (and
    # undefined in cp1252) — exactly the historical adopt-crash input.
    (repo / "c.txt").write_text("c\n", encoding="utf-8")
    _git(repo, "add", "c.txt")
    # Pass the message as a file so the raw byte survives the argv round-trip.
    msg_file = repo / "_msg"
    msg_file.write_bytes(b"fix \x9d control byte")
    _git(repo, "commit", "-F", str(msg_file))
    msg_file.unlink()
    return repo


def test_run_git_does_not_crash_on_non_ascii(cjk_git_repo: Path):
    """`_run_git` returns a str (no UnicodeDecodeError) on non-ASCII output."""
    out = _run_git(["log", "--format=%s"], cjk_git_repo)
    assert isinstance(out, str)
    assert "重构" in out
    assert "рефакторинг" in out


def test_analyze_git_runs_over_non_ascii_repo(cjk_git_repo: Path):
    """The full analyzer completes over a non-ASCII repo without crashing.

    Scope is the UTF-8 decode (WP7/F23) only — `analyze_git` must return a
    complete result dict over a repo whose subjects are CJK/Cyrillic. The
    `major_refactor_commits` *content* depends on a separate (pre-existing)
    numstat-parsing path that is out of this iterate's scope, so this asserts
    structure + the decoded log surface via `_run_git`, not major detection.
    """
    result = analyze_git(cjk_git_repo)
    assert result["commits_total"] == 3
    assert isinstance(result["major_refactor_commits"], list)
    # The Cyrillic + CJK subjects must round-trip intact through the raw log
    # that analyze_git consumes (no mojibake of the non-ASCII subjects).
    log = _run_git(["log", "--no-merges", "--format=%H|%s|%ai|%an"], cjk_git_repo)
    assert "рефакторинг migrate большой переезд" in log
    assert "重构 refactor 配置加载" in log


def test_analyze_git_replaces_invalid_byte_without_crash(cjk_git_repo: Path):
    """The 0x9D-byte commit is decoded with errors='replace', not a crash.

    The subject is invalid UTF-8 in its raw form; `errors='replace'` turns
    the bad byte into U+FFFD rather than raising. The analyzer must still
    return a complete result.
    """
    result = analyze_git(cjk_git_repo)
    assert result["commits_total"] == 3
    assert isinstance(result["contributors"], list)
