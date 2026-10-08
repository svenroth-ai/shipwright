"""``check_cascade_trigger`` when an input is unknown: triggered, never quiet.

An unmeasurable diff or an unreadable risk-flag source makes the run triggered,
and the review record decides: a reviewed ``code`` row passes, an unanswered one
fails with a repair. Only a git failure on the work tree itself fails outright.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import (  # noqa: E402, F401 - hermetic_git is an autouse fixture
    REVIEWED,
    RUN,
    check,
    commit_file,
    git,
    hermetic_git,
    init_repo,
    lines,
    make_repo,
    write_run,
)
from tools.verifiers import _cascade_trigger_inputs as inputs  # noqa: E402
from tools.verifiers import cascade_trigger as ct  # noqa: E402


def _baseless_repo(tmp_path: Path, shape: str) -> tuple[Path, str]:
    """A small change with no trunk base the gate can trust."""
    if shape == "remote-without-trunk-ref":
        root, sha = make_repo(tmp_path, {"src/a.py": lines(5)}, origin=False)
        git(root, "remote", "add", "origin", "https://example.invalid/repo.git")
        return root, sha
    return make_repo(tmp_path, {"src/a.py": lines(5)}, origin=False, trunk="develop")


_SHAPES = ["remote-without-trunk-ref", "trunk-named-develop"]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("shape", _SHAPES)
def test_an_unmeasurable_diff_is_triggered_and_free_text_fails(tmp_path, shape):
    root, sha = _baseless_repo(tmp_path, shape)
    write_run(root)
    result = check(root, sha)
    assert not result.ok
    assert "diff size unknown" in result.detail and "git fetch origin <trunk>" in result.detail
    assert "git fetch --unshallow" in result.detail


def _local_trunk_repo(tmp_path: Path, shape: str) -> tuple[Path, str]:
    """145 lines over two commits on a local ``main`` no remote trunk contains; 5-line tip."""
    root = tmp_path / "repo"
    init_repo(root)
    commit_file(root, "base.txt", "b\n", "base")
    if shape == "unpushed-main":
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    commit_file(root, "src/a.py", lines(140), "bulk")
    return root, commit_file(root, "src/b.py", lines(5), "tiny tip")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("shape", ["remote-less", "unpushed-main"])
def test_a_tip_on_a_local_only_trunk_is_unknown_not_measured_alone(tmp_path, shape):
    root, sha = _local_trunk_repo(tmp_path, shape)
    write_run(root)
    result = check(root, sha)
    assert not result.ok and "diff size unknown" in result.detail
    assert "5 changed lines" not in result.detail
    write_run(root, code=REVIEWED)
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("shape", _SHAPES)
def test_an_unmeasurable_diff_with_a_reviewed_code_row_passes(tmp_path, shape):
    root, sha = _baseless_repo(tmp_path, shape)
    write_run(root, code=REVIEWED)
    result = check(root, sha)
    assert result.ok and "diff size unknown" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_merge_commit_on_the_trunk_is_unknown(tmp_path):
    root, _ = make_repo(tmp_path, {"src/a.py": lines(150)})
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", "merge", "iterate/probe")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    write_run(root)
    result = check(root, git(root, "rev-parse", "HEAD"))
    assert not result.ok and "merge commit" in result.detail


@pytest.mark.covers("FR-01.11")
def test_is_merge_tells_a_git_failure_from_a_merge(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    assert inputs._is_merge(root, sha) is False
    assert inputs._is_merge(root, "0" * 40) is None


def _plan_path(root: Path) -> Path:
    return root / ".shipwright" / "agent_docs" / "iterates" / f"{RUN}.plan.json"


def _corrupt_plan(root: Path) -> None:
    _plan_path(root).write_text("{", encoding="utf-8")


def _foreign_plan(root: Path) -> None:
    _plan_path(root).write_text(json.dumps({"run_id": "iterate-2026-01-01-someone-else",
                                            "risk_flags": []}), encoding="utf-8")


def _plan_is_a_directory(root: Path) -> None:
    _plan_path(root).mkdir()


def _plan_without_run_id(root: Path) -> None:
    _plan_path(root).write_text(json.dumps({"risk_flags": []}), encoding="utf-8")


def _foreign_recheck(root: Path) -> None:
    path = root / ".shipwright" / "planning" / "iterate" / RUN / "risk_recheck.json"
    path.write_text(json.dumps({"schema_version": 1, "run_id": "iterate-2026-01-01-someone-else",
                                "risk_recheck": {"risk_flags": [], "effective_complexity": "small"}}),
                    encoding="utf-8")


_BAD_INPUTS = [
    (_corrupt_plan, "unreadable"),
    (_foreign_plan, "belongs to another run"),
    (_plan_is_a_directory, "not a regular file"),
    (_plan_without_run_id, "carries no `run_id`"),
    (_foreign_recheck, "another run"),
]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("spoil,why", _BAD_INPUTS)
def test_an_unreadable_flag_source_is_triggered_and_free_text_fails(tmp_path, spoil, why):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    write_run(root)
    spoil(root)
    result = check(root, sha)
    assert not result.ok and "risk flags unknown" in result.detail and why in result.detail
    assert "regenerate or remove" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("spoil,why", _BAD_INPUTS)
def test_an_unreadable_flag_source_with_a_reviewed_code_row_passes(tmp_path, spoil, why):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    write_run(root, code=REVIEWED)
    spoil(root)
    result = check(root, sha)
    assert result.ok and why in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_symlinked_plan_is_refused(tmp_path):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    write_run(root)
    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps({"run_id": RUN, "risk_flags": []}), encoding="utf-8")
    try:
        _plan_path(root).symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create a symlink here")
    result = check(root, sha)
    assert not result.ok and "symlink" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_plan_read_through_a_symlinked_directory_is_refused(tmp_path):
    root = tmp_path / "proj"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / f"{RUN}.plan.json").write_text(json.dumps({"run_id": RUN, "risk_flags": []}),
                                                encoding="utf-8")
    (root / ".shipwright" / "agent_docs").mkdir(parents=True)
    try:
        (root / ".shipwright" / "agent_docs" / "iterates").symlink_to(elsewhere, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create a symlink here")
    data, err = inputs.read_plan(root, RUN)
    assert data is None and "resolves outside" in err


@pytest.mark.covers("FR-01.11")
def test_a_flagged_non_git_directory_fires(tmp_path, monkeypatch):
    root = tmp_path / "plain"
    root.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    write_run(root, plan_flags=["touches_auth"])
    result = ct.check_cascade_trigger(root, RUN, "")
    assert not result.ok and "touches_auth" in result.detail
    write_run(root, plan_flags=[])
    assert ct.check_cascade_trigger(root, RUN, "").detail.startswith("skipped")


@pytest.mark.covers("FR-01.11")
def test_a_git_error_fails_closed(tmp_path, monkeypatch):
    root, sha = make_repo(tmp_path, {"src/a.py": lines(3)})
    write_run(root, code=REVIEWED)
    monkeypatch.setattr(ct, "git_context", lambda _root: "git_error")
    result = check(root, sha)
    assert not result.ok and "Fix git first" in result.detail
