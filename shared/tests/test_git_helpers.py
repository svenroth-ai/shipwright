"""Tests for the shared verifier git wrappers (``verifiers/git_helpers.py``).

Covers the contract that ``spec_checks`` now folds onto
(iterate-2026-06-13-shc-git-helpers):

- ``_run_git`` keeps its ``git -C`` form and ``(rc, out, err)`` contract.
- The new optional ``timeout`` param passes through to ``subprocess.run``
  only when set; the default ``None`` preserves the original no-timeout
  behaviour for existing callers.
- A ``TimeoutExpired`` is swallowed and reported as ``(1, "", "")`` — the
  unified failure code (git_helpers returns ``1``, never ``-1``).
- ``_git_available`` is truthy on a real repo and false off-repo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tools.verifiers import git_helpers as gh  # noqa: E402


def _init_git_repo(proj: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(proj), check=False)
    subprocess.run(
        ["git", "config", "user.email", "t@test"], cwd=str(proj), check=False,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"], cwd=str(proj), check=False,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], cwd=str(proj), check=False,
    )


# ---------------------------------------------------------------------------
# Real-repo contract
# ---------------------------------------------------------------------------


def test_run_git_returns_tuple_on_real_repo(tmp_path: Path):
    _init_git_repo(tmp_path)
    rc, out, err = gh._run_git(tmp_path, "rev-parse", "--is-inside-work-tree")
    assert rc == 0
    assert out.strip() == "true"


def test_git_available_true_on_repo_false_off_repo(tmp_path: Path):
    off = tmp_path / "not-a-repo"
    off.mkdir()
    assert gh._git_available(off) is False
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    assert gh._git_available(repo) is True


# ---------------------------------------------------------------------------
# Failure code: unified on 1 (never -1)
# ---------------------------------------------------------------------------


def test_run_git_returns_1_on_missing_binary(monkeypatch, tmp_path: Path):
    """OSError (e.g. git binary missing) → (1, "", "") — the unified
    failure code spec_checks now shares (it previously returned -1)."""
    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _boom)
    rc, out, err = gh._run_git(tmp_path, "status")
    assert rc == 1
    assert out == "" and err == ""


# ---------------------------------------------------------------------------
# New optional timeout param
# ---------------------------------------------------------------------------


def test_run_git_default_omits_timeout_kwarg(monkeypatch, tmp_path: Path):
    """Default (no timeout arg) does NOT pass ``timeout`` to subprocess.run at
    all — the kwarg shape is identical to the pre-param call, preserving exact
    behaviour for existing callers (timeout is forwarded ONLY when set)."""
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_run(args, **kwargs):
        captured["kwargs"] = kwargs
        return _Proc()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc, out, _ = gh._run_git(tmp_path, "status")
    assert rc == 0 and out == "ok"
    assert "timeout" not in captured["kwargs"]


def test_run_git_passes_explicit_timeout(monkeypatch, tmp_path: Path):
    """An explicit ``timeout=`` is forwarded to subprocess.run unchanged
    (this is the behaviour spec_checks preserves with ``timeout=10.0``)."""
    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(args, **kwargs):
        captured["timeout"] = kwargs.get("timeout", "MISSING")
        return _Proc()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    gh._run_git(tmp_path, "log", timeout=10.0)
    assert captured["timeout"] == 10.0


def test_run_git_swallows_timeout_expired_as_failure(monkeypatch, tmp_path: Path):
    """A TimeoutExpired is caught and reported as the unified (1, '', '')
    failure (spec_checks previously returned -1 for this path)."""
    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=10.0)

    monkeypatch.setattr(subprocess, "run", _timeout)
    rc, out, err = gh._run_git(tmp_path, "log", timeout=10.0)
    assert rc == 1
    assert out == "" and err == ""
