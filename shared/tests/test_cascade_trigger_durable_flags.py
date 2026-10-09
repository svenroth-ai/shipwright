"""``check_cascade_trigger``: the F5c entry's durable ``risk_flags``, and a rebase-merged PR measured whole.

U4 follow-ups. A small run with no ``plan.json`` and no ``risk_recheck.json`` used to read as "no
flags"; it now needs the entry's own list. A PR rebase-merged onto the trunk lands as several commits,
each stamped ``Run-ID:``, and is measured as one change instead of by its last commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import (  # noqa: E402, F401 - hermetic_git is an autouse fixture
    RUN,
    REVIEWED,
    check,
    commit_file,
    git,
    hermetic_git,
    lines,
    make_repo,
    not_run,
    write_run,
)


def _quiet_repo(tmp_path):
    return make_repo(tmp_path, {"src/a.py": lines(3)})


@pytest.mark.covers("FR-01.11")
def test_a_run_with_no_plan_no_recheck_and_no_entry_flags_is_unknown_not_quiet(tmp_path):
    root, sha = _quiet_repo(tmp_path)
    write_run(root, entry_flags=None)
    result = check(root, sha)
    assert not result.ok and "risk flags unknown" in result.detail and "never recorded" in result.detail
    assert "Add `risk_flags" in result.detail and "unreadable file" not in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_recorded_empty_list_is_an_answer_and_the_run_is_quiet(tmp_path):
    root, sha = _quiet_repo(tmp_path)
    write_run(root, entry_flags=[])
    result = check(root, sha)
    assert result.ok and "not triggered" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_flag_in_the_entry_alone_triggers_the_review(tmp_path):
    root, sha = _quiet_repo(tmp_path)
    write_run(root, entry_flags=["touches_auth"])
    result = check(root, sha)
    assert not result.ok and "risk flag(s) touches_auth" in result.detail
    write_run(root, entry_flags=["touches_auth"], code={**REVIEWED})
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("bad", ["touches_auth", [1], ["", "touches_auth"], {"touches_auth": True}])
def test_a_malformed_entry_list_is_unknown_never_empty(tmp_path, bad):
    root, sha = _quiet_repo(tmp_path)
    write_run(root, entry_flags=bad)
    result = check(root, sha)
    assert not result.ok and "not a list of flag names" in result.detail


@pytest.mark.covers("FR-01.11")
def test_the_entry_list_and_the_plan_are_unioned(tmp_path):
    root, sha = _quiet_repo(tmp_path)
    write_run(root, plan_flags=["touches_rls"], entry_flags=["touches_auth"])
    result = check(root, sha)
    assert not result.ok and "touches_auth, touches_rls" in result.detail


def _rebase_merged(tmp_path, sizes, trailer=True):
    """A trunk (``main`` + ``origin/main``) whose last commits are the run's, one per size."""
    root, _ = make_repo(tmp_path, {"src/other.py": lines(5)})
    git(root, "checkout", "-q", "main")
    tip = ""
    for i, n in enumerate(sizes):
        message = f"feat: part {i}" + (f"\n\nRun-ID: {RUN}" if trailer else "")
        tip = commit_file(root, f"src/part{i}.py", lines(n), message)
    git(root, "update-ref", "refs/remotes/origin/main", tip)
    return root, tip


@pytest.mark.covers("FR-01.11")
def test_a_rebase_merged_multi_commit_pr_is_measured_as_a_whole(tmp_path):
    root, tip = _rebase_merged(tmp_path, [60, 60, 3])
    write_run(root)
    result = check(root, tip)
    assert not result.ok and "123 changed lines > 100" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_rebase_merged_pr_counts_only_its_own_commits(tmp_path):
    root, _ = make_repo(tmp_path, {"src/other.py": lines(5)})
    git(root, "checkout", "-q", "main")
    commit_file(root, "src/big_other.py", lines(500), "feat: another PR\n\nRun-ID: iterate-2026-10-09-someone-else")
    tip = commit_file(root, "src/mine.py", lines(3), f"feat: mine\n\nRun-ID: {RUN}")
    git(root, "update-ref", "refs/remotes/origin/main", tip)
    write_run(root)
    result = check(root, tip)
    assert result.ok and "3 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_without_the_trailer_the_tip_alone_is_measured_as_before(tmp_path):
    root, tip = _rebase_merged(tmp_path, [60, 60, 3], trailer=False)
    write_run(root)
    result = check(root, tip)
    assert result.ok and "3 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_prefix_colliding_run_id_and_a_body_mention_are_not_this_run(tmp_path):
    root, _ = make_repo(tmp_path, {"src/other.py": lines(5)})
    git(root, "checkout", "-q", "main")
    commit_file(root, "src/a.py", lines(200), f"feat: sibling\n\nRun-ID: {RUN}-2")
    commit_file(root, "src/b.py", lines(200), f"revert: quotes\n\nthe old footer said Run-ID: {RUN} here\n\nRun-ID: iterate-2026-10-09-x")
    commit_file(root, "src/c.py", lines(200), "feat: foreign in between\n\nRun-ID: iterate-2026-10-09-y")
    tip = commit_file(root, "src/mine.py", lines(3), f"feat: mine\n\nRun-ID: {RUN}")
    git(root, "update-ref", "refs/remotes/origin/main", tip)
    write_run(root)
    result = check(root, tip)
    assert result.ok and "3 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_git_failure_listing_the_run_commits_is_unknown_not_tip_only(tmp_path, monkeypatch):
    from tools.verifiers import _cascade_trigger_inputs as inputs
    real = inputs._run_git

    def failing(root, *args, **kw):
        return (1, "", "boom") if args[:1] == ("log",) else real(root, *args, **kw)

    monkeypatch.setattr(inputs, "_run_git", failing)
    root, sha = _quiet_repo(tmp_path)
    assert inputs._run_commits(root, sha, RUN) is None


@pytest.mark.covers("FR-01.11")
def test_the_run_id_trailer_counts_whatever_trailer_lines_follow_it(tmp_path):
    from tools.verifiers import _cascade_trigger_inputs as inputs
    root, _ = _quiet_repo(tmp_path)
    tail = f"Run-ID: {RUN}\n\nCo-Authored-By: A <a@x.y>\nCo-Authored-By: B <b@x.y>\nSigned-off-by: C <c@x.y>"
    earlier = commit_file(root, "src/b.py", lines(2), message=f"feat: x\n\n{tail}")
    head = commit_file(root, "src/c.py", lines(2), message="feat: y")
    assert earlier in inputs._run_commits(root, head, RUN)


@pytest.mark.covers("FR-01.11")
def test_an_explicit_null_entry_list_is_unknown_not_absent(tmp_path):
    from tools.verifiers._cascade_trigger_inputs import recorded_risk_flags
    flags, err = recorded_risk_flags(tmp_path, RUN, {"risk_flags": None})
    assert flags == [] and err and "null" in err


@pytest.mark.covers("FR-01.11")
def test_the_entrys_own_risk_recheck_flags_count(tmp_path):
    from tools.verifiers._cascade_trigger_inputs import recorded_risk_flags
    flags, err = recorded_risk_flags(tmp_path, RUN, {"risk_flags": [], "risk_recheck": {"risk_flags": ["touches_auth"]}})
    assert err is None and flags == ["touches_auth"]
