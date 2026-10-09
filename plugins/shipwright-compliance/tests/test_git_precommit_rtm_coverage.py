"""The git-side coverage gate: real ``git commit`` in temp repos with the real ``pre-commit``.

``core.hooksPath`` points at the monorepo's ``scripts/hooks``; git itself runs the hook, so every
shell shape that led to the commit is irrelevant (AC-9).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
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
    init_repo,
    hook_env,
    log_override,
    release_token,
    make_repo,
    scrub_git_env,
    stage_manifest,
    write_manifest,
)

pytestmark = pytest.mark.covers("FR-01.10")


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path)


def test_blocks_below_threshold(repo):  # AC-1
    stage_manifest(repo, 1)
    result = commit(repo)
    assert result.returncode != 0
    assert BLOCKED in result.stderr
    assert "1/2" in result.stderr
    assert head_count(repo) == 1


def test_allows_at_threshold_and_prints_figure(repo):  # AC-2
    git(repo, "commit", "-q", "--allow-empty", "-m", "noop")  # hook runs, 2/2 in HEAD
    stage_manifest(repo, 2, source_commit="b" * 40)
    result = commit(repo)
    assert result.returncode == 0, result.stderr
    assert "2/2" in result.stdout + result.stderr


def test_commit_a_judges_the_staged_copy_not_head(repo):  # AC-3 (HEAD good, worktree bad)
    write_manifest(repo, collector_manifest(1, 2))  # modified, NOT staged
    result = commit(repo, "-a")
    assert result.returncode != 0 and BLOCKED in result.stderr


def test_commit_a_good_worktree_over_bad_head(repo):  # AC-3 (reverse)
    stage_manifest(repo, 1)
    git(repo, "-c", "core.hooksPath=" + str(repo / ".no-hooks"), "commit", "-q", "-m", "bad")
    write_manifest(repo, collector_manifest(2, 2, source_commit="c" * 40))
    result = commit(repo, "-a")
    assert result.returncode == 0, result.stderr


def test_pathspec_commit_judges_the_staged_copy(repo):  # AC-3
    write_manifest(repo, collector_manifest(1, 2))
    result = commit(repo, str(REL))
    assert result.returncode != 0 and BLOCKED in result.stderr


def test_no_compliance_data_commits(tmp_path):  # AC-4
    init_repo(tmp_path)
    git(tmp_path, "config", "core.hooksPath", str(HOOKS))
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    git(tmp_path, "add", "-A")
    result = commit(tmp_path)
    assert result.returncode == 0 and "WARN" not in result.stderr


def test_non_current_schema_warns_and_commits(repo):  # AC-4
    stage_manifest(repo, 0, schema_version=1)
    result = commit(repo)
    assert result.returncode == 0, result.stderr
    assert "WARN" in result.stderr


def test_no_executed_result_warns_and_commits(repo):  # AC-4
    stage_manifest(repo, 0, executed_rest="not_run")
    result = commit(repo)
    assert result.returncode == 0, result.stderr
    assert "WARN" in result.stderr and "NOT evaluating" in result.stderr


def test_token_is_removed_even_when_the_manifest_is_unmeasurable(repo):  # AC-7
    sys.path.insert(0, str(LIB))
    try:
        import git_side_release
    finally:
        sys.path.remove(str(LIB))
    release_token(repo, "check_rtm_coverage")
    stage_manifest(repo, 0, schema_version=1)
    assert commit(repo).returncode == 0
    assert not git_side_release.token(repo, "check_rtm_coverage").exists()


def test_logged_override_releases_once(repo):  # AC-6
    stage_manifest(repo, 1)
    assert commit(repo).returncode != 0
    log_override(repo)
    released = commit(repo)
    assert released.returncode == 0, released.stderr
    assert "OVERRIDDEN once" in released.stderr
    assert "CONSUMED" in (repo / LOG).read_text(encoding="utf-8")
    stage_manifest(repo, 1, source_commit="d" * 40)
    again = commit(repo)
    assert again.returncode != 0 and BLOCKED in again.stderr


def test_handoff_token_covers_one_git_side_run(repo):  # AC-7
    sys.path.insert(0, str(LIB))
    try:
        pass
    finally:
        sys.path.remove(str(LIB))
    stage_manifest(repo, 1)
    release_token(repo, "check_rtm_coverage")
    released = commit(repo)
    assert released.returncode == 0, released.stderr
    assert "already used" in released.stderr
    stage_manifest(repo, 1, source_commit="e" * 40)
    assert commit(repo).returncode != 0  # token was taken by exactly one run


@pytest.mark.parametrize("wrapper", ["git $'commit'", "uv run --no-project git commit"])
def test_shapes_the_lexer_misses_are_caught_at_the_real_commit(repo, wrapper):  # AC-9
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available on this platform")
    sys.path.insert(0, str(LIB))
    try:
        from git_commit_command import is_git_commit
    finally:
        sys.path.remove(str(LIB))
    shape = f"{wrapper} -q -m x"
    if is_git_commit(shape):  # a later lexer reads it: this shape no longer proves the class
        pytest.skip(f"the lexer reads {wrapper!r} now")
    stage_manifest(repo, 1)
    result = subprocess.run([bash, "-c", shape], cwd=repo, capture_output=True, text=True,
                            env=hook_env(repo), timeout=120)
    assert result.returncode != 0 and BLOCKED in result.stderr, result.stderr
    assert head_count(repo) == 1


def test_anti_ratchet_step_and_coverage_step_are_both_wired():  # AC-8
    text = (HOOKS / "pre-commit").read_text(encoding="utf-8")
    assert "anti_ratchet_check.py" in text and "git_precommit_rtm_coverage.py" in text
    assert text.index("anti_ratchet_check.py") < text.index("git_precommit_rtm_coverage.py")
    assert (SCRIPT_DIR / "git_precommit_rtm_coverage.py").is_file()


def test_token_expires_and_has_a_single_winner(tmp_path):
    sys.path.insert(0, str(LIB))
    try:
        import git_side_release
    finally:
        sys.path.remove(str(LIB))
    hook = "check_rtm_coverage"
    assert git_side_release.take(tmp_path, hook) is False
    found = release_token(tmp_path, hook)
    assert git_side_release.take(tmp_path, hook) is True
    assert git_side_release.take(tmp_path, hook) is False
    git_side_release.grant(tmp_path, hook, found.at)  # same consumed entry, re-stamped
    later = datetime.now(timezone.utc).timestamp() + 3600
    assert git_side_release.take(tmp_path, hook, now=later) is False
    assert not git_side_release.token(tmp_path, hook).exists()


def _install_hook(hooks: Path) -> None:
    """Copy the real pre-commit LF-normalised and executable (git ignores a non-executable hook)."""
    target = hooks / "pre-commit"
    target.write_bytes((HOOKS / "pre-commit").read_bytes().replace(b"\r\n", b"\n"))
    target.chmod(0o755)


def _fake_framework(tmp_path: Path, body: str) -> Path:
    """A copy of the real pre-commit beside a stand-in coverage script running *body*."""
    hooks = tmp_path / "fw" / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    _install_hook(hooks)
    script =tmp_path / "fw" / "plugins" / "shipwright-compliance" / "scripts" / "hooks"
    script.mkdir(parents=True)
    (script / "git_precommit_rtm_coverage.py").write_text(body, encoding="utf-8")
    return hooks


@pytest.mark.parametrize("body", ["raise SystemExit(1)", "def (:\n", "import sys; sys.exit(7)"])
def test_interpreter_or_script_failure_fails_open_with_a_warn(repo, tmp_path_factory, body):
    hooks = _fake_framework(tmp_path_factory.mktemp("fw"), body)
    git(repo, "config", "core.hooksPath", str(hooks))
    stage_manifest(repo, 1)
    result = commit(repo)
    assert result.returncode == 0, result.stderr
    assert "NOT evaluating" in result.stderr


def test_missing_coverage_script_warns_and_commits(repo, tmp_path_factory):  # AC-8
    root = tmp_path_factory.mktemp("fw")
    hooks = root / "fw" / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    _install_hook(hooks)
    git(repo, "config", "core.hooksPath", str(hooks))
    stage_manifest(repo, 1)
    result = commit(repo)
    assert result.returncode == 0, result.stderr
    assert "not found" in result.stderr and "NOT evaluating" in result.stderr


def test_exit_three_is_the_only_block(repo, tmp_path_factory):
    hooks = _fake_framework(tmp_path_factory.mktemp("fw"), "raise SystemExit(3)")
    git(repo, "config", "core.hooksPath", str(hooks))
    stage_manifest(repo, 1)
    assert commit(repo).returncode != 0


def test_orphan_token_is_removed_by_the_next_run_and_cannot_bypass_later(repo):
    sys.path.insert(0, str(LIB))
    try:
        import git_side_release
    finally:
        sys.path.remove(str(LIB))
    release_token(repo, "check_rtm_coverage")
    git(repo, "commit", "-q", "--allow-empty", "-m", "moves HEAD", "--no-verify")
    stage_manifest(repo, 1)
    result = commit(repo)  # token bound to the old HEAD: not honoured, and gone afterwards
    assert result.returncode != 0 and BLOCKED in result.stderr
    assert not git_side_release.token(repo, "check_rtm_coverage").exists()


def test_override_reason_outside_cp1252_does_not_turn_a_release_into_a_crash(repo):
    stage_manifest(repo, 1)
    path = repo / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(f"{stamp} | check_rtm_coverage | OVERRIDE | 是的 continue ✓\n", encoding="utf-8")
    result = commit(repo)
    assert result.returncode == 0, result.stderr
    assert "OVERRIDDEN once" in result.stderr
