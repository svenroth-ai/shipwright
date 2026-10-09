"""The git-side coverage gate and its PreToolUse producer, run in-process (visible to coverage)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if str(Path(__file__).parent) not in sys.path:  # sibling support module
    sys.path.insert(0, str(Path(__file__).parent))
from git_precommit_test_support import (  # noqa: E402, F401 - scrub_git_env is autouse
    BLOCKED,
    HOOKS,
    LIB,
    LOG,
    REL,
    SCRIPT_DIR,
    collector_manifest,
    commit,
    git,
    head_count,
    hook_env,
    log_override,
    release_token,
    make_repo,
    scrub_git_env,
    stage_manifest,
)

pytestmark = pytest.mark.covers("FR-01.10")


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


@pytest.fixture
def step(monkeypatch, repo):
    """The git-side module imported in-process, cwd = the temp repo (never the real checkout)."""
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "path", list(sys.path))  # the script prepends shared/ and lib/
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    monkeypatch.syspath_prepend(str(LIB))
    sys.modules.pop("git_precommit_rtm_coverage", None)
    import git_precommit_rtm_coverage as module

    return module


def test_internal_error_fails_open(step, monkeypatch, capsys):  # AC-5
    import rtm_gate_support

    def boom(_root):
        raise RuntimeError("boom")

    monkeypatch.setattr(rtm_gate_support, "measure", boom)
    assert step.main() == 0
    assert "NOT evaluating" in capsys.readouterr().err


def test_check_blocks_with_exit_three_below_threshold(step, repo, capsys):  # AC-1
    stage_manifest(repo, 1)
    assert step.main() == step.BLOCK == 3
    assert BLOCKED in capsys.readouterr().err


def test_check_allows_at_threshold(step, repo, capsys):  # AC-2
    assert step.main() == 0
    assert "2/2" in capsys.readouterr().out


def test_check_honours_the_handoff_token_once(step, repo, capsys):  # AC-7

    stage_manifest(repo, 1)
    release_token(repo, step.HOOK)
    assert step.main() == 0
    assert "already used" in capsys.readouterr().err
    assert step.main() == step.BLOCK


def test_check_releases_through_a_logged_override(step, repo, capsys):  # AC-6
    stage_manifest(repo, 1)
    log_override(repo)
    assert step.main() == 0
    assert "OVERRIDDEN once" in capsys.readouterr().err
    assert step.main() == step.BLOCK


def test_pretooluse_release_writes_the_token_the_git_side_takes(monkeypatch, repo):  # AC-7
    """The producer side: an override release in the Claude hook leaves a HEAD-bound token."""
    import io
    import json

    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    monkeypatch.syspath_prepend(str(LIB))
    sys.modules.pop("check_rtm_coverage", None)
    import check_rtm_coverage
    import git_side_release

    stage_manifest(repo, 1)
    git(repo, "commit", "-q", "-m", "bad base", "--no-verify")  # HEAD itself now below threshold
    log_override(repo)
    payload = {"tool_input": {"command": "git commit -m x"}, "cwd": str(repo)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert check_rtm_coverage.main() == 0
    token = git_side_release.token(repo, "check_rtm_coverage")
    assert token.read_text(encoding="utf-8").splitlines()[0] == git_side_release.head(repo)
    assert git_side_release.take(repo, "check_rtm_coverage") is True


def test_expired_handoff_is_named_in_the_block(step, repo, capsys):  # AC-7
    import os
    import time

    import git_side_release

    stage_manifest(repo, 1)
    release_token(repo, step.HOOK)
    old = time.time() - 600
    os.utime(git_side_release.token(repo, step.HOOK), (old, old))
    assert step.main() == step.BLOCK
    assert "hand-off lasts" in capsys.readouterr().err


def test_junk_token_is_removed_and_evaluation_continues(step, repo, capsys):  # AC-7
    import git_side_release

    stage_manifest(repo, 1)
    path = git_side_release.token(repo, step.HOOK)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe\x00junk")
    assert step.main() == step.BLOCK
    assert not path.exists()


def test_hand_written_token_without_a_consumed_override_is_refused(step, repo, capsys):  # AC-7
    import git_side_release

    stage_manifest(repo, 1)
    path = git_side_release.token(repo, step.HOOK)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{git_side_release.head(repo)}\n2026-10-09T00:00:00+00:00", encoding="utf-8")
    assert step.main() == step.BLOCK
    assert "names no consumed override" in capsys.readouterr().err
    assert not path.exists()
