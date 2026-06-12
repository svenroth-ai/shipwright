"""UTF-8 regression tests for the shared git-reading tools (deep-audit WP7).

Two shared tools decode `git` subprocess output with `text=True` but no
explicit `encoding=`, so on a Windows dev box git's UTF-8 byte stream is
decoded with the platform default (cp1252):

* F26 — ``generate_session_handoff.get_git_info`` reads ``git log -1
  --oneline``; a non-ASCII commit subject is mojibaked into the TRACKED
  ``session_handoff.md`` (or crashes on an undecodable byte).
* F27 — ``repo_root.resolve_main_repo_root`` reads ``git rev-parse
  --git-common-dir``; a non-ASCII project path is mojibaked, so the
  resolved main root does not exist and worktree decision-drops are
  silently lost.

Both are exercised against REAL git repos whose paths / commit subjects
carry CJK + Cyrillic + accented characters — no mocks of the decode.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lib.repo_root import resolve_main_repo_root
from tools.generate_session_handoff import get_git_info


def _git(cwd: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Иван Tester",
            "GIT_AUTHOR_EMAIL": "i@test.invalid",
            "GIT_COMMITTER_NAME": "Иван Tester",
            "GIT_COMMITTER_EMAIL": "i@test.invalid",
        }
    )
    subprocess.run(["git", *args], cwd=str(cwd), env=env, check=True,
                   capture_output=True)


# --------------------------------------------------------------------------- #
# F26 — get_git_info commit-subject decode
# --------------------------------------------------------------------------- #


@pytest.fixture
def cjk_commit_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "初回コミット — café déjà vu 配置")
    return repo


def test_get_git_info_decodes_non_ascii_subject(cjk_commit_repo: Path):
    """The last-commit line round-trips the CJK/accented subject (no mojibake).

    Pre-fix on cp1252 the bytes were decoded wrong, embedding garbage like
    ``åˆ�å›�`` into the tracked session_handoff.md (or raising on an
    undecodable byte). The subject must come back intact.
    """
    info = get_git_info(cjk_commit_repo)
    assert "error" not in info
    assert "初回コミット" in info["last_commit"]
    assert "café déjà vu" in info["last_commit"]


def test_get_git_info_branch_and_status_present(cjk_commit_repo: Path):
    """Sanity: the other git reads still populate even with a non-ASCII repo."""
    info = get_git_info(cjk_commit_repo)
    assert info["branch"] == "main"
    # Clean tree => no uncommitted changes string.
    assert info["uncommitted_changes"] == ""


# --------------------------------------------------------------------------- #
# F27 — resolve_main_repo_root on an accented path
# --------------------------------------------------------------------------- #


@pytest.fixture
def accented_repo(tmp_path: Path):
    """A main repo whose path carries accented + CJK characters, plus a
    linked worktree under it. ``git rev-parse --git-common-dir`` returns a
    path with those bytes; a cp1252 decode mojibakes it into a non-existent
    directory."""
    base = tmp_path / "café-プロジェクト"
    work = base / "work"
    work.mkdir(parents=True)
    _git(work, "init", "-b", "main")
    (work / "r.txt").write_text("r\n", encoding="utf-8")
    _git(work, "add", "r.txt")
    _git(work, "commit", "-m", "init")
    wt = base / "wt"
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt), "-b", "iterate/x", "main"],
        check=True, capture_output=True,
    )
    return work, wt


def test_resolve_main_root_from_accented_main(accented_repo):
    """From the main repo under an accented path the resolved root exists
    and equals the repo root (no mojibake to a non-existent dir)."""
    work, _wt = accented_repo
    resolved = resolve_main_repo_root(work)
    assert resolved is not None
    assert resolved.exists()
    assert resolved.resolve() == work.resolve()


def test_resolve_main_root_from_accented_worktree(accented_repo):
    """From a linked worktree under an accented path, resolution returns the
    EXISTING main repo root — the F27 failure was a mojibaked (non-existent)
    path that silently lost worktree decision-drops."""
    work, wt = accented_repo
    resolved = resolve_main_repo_root(wt)
    assert resolved is not None
    assert resolved.exists()
    assert resolved.resolve() == work.resolve()


def test_resolve_main_root_failsoft_on_nonexistent_common_dir(
    tmp_path: Path, monkeypatch, recwarn,
):
    """F27 guard in isolation: when `git rev-parse --git-common-dir` yields a
    path whose parent does NOT exist on disk (the mojibake failure mode),
    `resolve_main_repo_root` must return None — the documented fail-soft
    signal that callers translate to the literal project_root via
    `resolve_main_repo_root(...) or project_root`. Without the guard the
    function would hand back a phantom directory and decision-drops written
    there would be silently lost.
    """
    phantom = tmp_path / "does-not-exist" / ".git"

    class _Proc:
        returncode = 0
        stdout = str(phantom)

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    resolved = resolve_main_repo_root(tmp_path)
    assert resolved is None
    # The caller protocol: None -> literal project_root.
    assert (resolved or tmp_path) == tmp_path
    # The fail-soft is loud (diagnostic warning), not silent.
    assert any("does not exist" in str(w.message) for w in recwarn)
