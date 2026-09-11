"""FR-01.03 #7 / FR-01.04 #11 — a planning or design session writes no
production code. One generic prefix-boundary check, shared by both callers.
"""

import subprocess
from pathlib import Path

from lib.phase_write_boundary import find_boundary_violations, git_dirty_paths


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


# --------------------------------------------------------------------------- #
# find_boundary_violations — pure prefix logic
# --------------------------------------------------------------------------- #


def test_a_path_under_an_allowed_prefix_is_not_a_violation():
    assert find_boundary_violations(
        [".shipwright/planning/01-auth/plan.md"], [".shipwright/"]
    ) == []


def test_a_production_path_is_a_violation():
    assert find_boundary_violations(["src/app/api/route.ts"], [".shipwright/"]) == [
        "src/app/api/route.ts"
    ]


def test_matching_is_platform_invariant_on_separators():
    assert find_boundary_violations(
        ["src\\app\\route.ts"], [".shipwright/"]
    ) == ["src\\app\\route.ts"]
    assert find_boundary_violations(
        [".shipwright\\planning\\plan.md"], [".shipwright/"]
    ) == []


def test_no_changed_paths_means_no_violations():
    assert find_boundary_violations([], [".shipwright/"]) == []


def test_multiple_allowed_prefixes_all_apply():
    changed = [".shipwright/designs/screens/01-a.html", "shipwright_project_config.json", "src/x.py"]
    violations = find_boundary_violations(
        changed, [".shipwright/", "shipwright_project_config.json"]
    )
    assert violations == ["src/x.py"]


# --------------------------------------------------------------------------- #
# git_dirty_paths — real git evidence
# --------------------------------------------------------------------------- #


def test_a_clean_worktree_reports_no_dirty_paths(tmp_path):
    repo = _init_repo(tmp_path)
    assert git_dirty_paths(repo) == []


def test_an_untracked_file_is_reported(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "notes.md").write_text("x\n", encoding="utf-8")
    assert "notes.md" in git_dirty_paths(repo)


def test_a_modified_tracked_file_is_reported(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert "README.md" in git_dirty_paths(repo)


def test_a_nested_untracked_file_is_reported_with_posix_separators(tmp_path):
    repo = _init_repo(tmp_path)
    nested = repo / ".shipwright" / "planning" / "01-auth"
    nested.mkdir(parents=True)
    (nested / "plan.md").write_text("x\n", encoding="utf-8")
    dirty = git_dirty_paths(repo)
    assert ".shipwright/planning/01-auth/plan.md" in dirty
    assert all("\\" not in p for p in dirty)


def test_a_rename_reports_both_the_old_and_new_path(tmp_path):
    """A production file renamed INTO an allowed prefix must not make the
    old production path disappear from the evidence (external code review,
    iterate-2026-09-11-e1-checks-plan-design)."""
    repo = _init_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add production file")
    (repo / ".shipwright").mkdir()
    (repo / "src" / "app.py").rename(repo / ".shipwright" / "notes.md")
    _git(repo, "add", "-A")
    dirty = git_dirty_paths(repo)
    assert "src/app.py" in dirty
    assert ".shipwright/notes.md" in dirty
    violations = find_boundary_violations(dirty, [".shipwright/"])
    assert "src/app.py" in violations


def test_a_non_git_directory_yields_no_paths_rather_than_raising(tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    assert git_dirty_paths(not_a_repo) == []


def test_an_unrelated_pre_existing_dirty_path_is_also_reported(tmp_path):
    """Pins the module's documented, accepted scope (external plan review,
    iterate-2026-09-11-e1-checks-plan-design): there is no session-start
    baseline, so a file left dirty for a reason unrelated to the current
    phase session is indistinguishable from one this session wrote, and
    both are reported. Real call sites avoid this because a plan/design
    session runs in its own freshly-branched, still-clean worktree — this
    test documents the behaviour rather than treating it as a silent gap."""
    repo = _init_repo(tmp_path)
    (repo / "unrelated-leftover.txt").write_text("stray, not this session's\n", encoding="utf-8")
    dirty = git_dirty_paths(repo)
    assert "unrelated-leftover.txt" in dirty
    violations = find_boundary_violations(dirty, [".shipwright/"])
    assert "unrelated-leftover.txt" in violations
