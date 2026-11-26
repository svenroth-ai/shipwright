"""Stop 3, F-S3-1 (FINDINGS D109): after ``gh pr merge`` the checkout sits on the trunk at the merge commit, and the tag push
``release.py push-tag`` prints (``git push origin refs/tags/vX``) was judged as a trunk push, so HEAD (the merge commit) was
judged and the push denied. A push whose refspecs name only tags is not a trunk push: the tag's commit is judged.

Real git, the hook run as Claude Code runs it, on a merged-trunk fixture (the state of the live S2al-1 run)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "hooks"))
import release_guard as rg  # noqa: E402
from release_guard_commands import find_actions  # noqa: E402

from .test_release_guard import VERSION, blocked, git, repo as _repo, run_hook
from .test_release_guard_fix_round import _released_branch

repo = _repo  # the fixture, re-exported so pytest finds it in this module
pytestmark = pytest.mark.covers("FR-01.09/AC01")

TAG_ONLY = [f"git push origin refs/tags/v{VERSION}", f"git push origin v{VERSION}", f"git push origin tag v{VERSION}",
            "git push --tags", "git push --tags origin", f"git push origin +refs/tags/v{VERSION}:refs/tags/v{VERSION}",
            f"git push origin v{VERSION}:refs/tags/v{VERSION}"]
WITH_THE_TRUNK = ["git push origin main", f"git push --atomic origin main refs/tags/v{VERSION}", f"git push origin tag v{VERSION} main",
                  "git push --follow-tags", "git push --follow-tags origin", "git push --tags origin main", f"git push origin HEAD refs/tags/v{VERSION}",
                  # the remote tag made from another commit (code review, stop 3): judged by HEAD as before F-S3-1
                  f"git push origin HEAD:refs/tags/v{VERSION}", f"git push origin main:refs/tags/v{VERSION}",
                  f"git push origin refs/tags/v{VERSION} HEAD:refs/tags/v9.9.9",
                  # the matching refspec pushes every matching branch, main included (doubt review, stop 3)
                  f"git push origin : refs/tags/v{VERSION}", f"git push origin +: tag v{VERSION}", "git push origin : --tags"]


@pytest.fixture
def merged_trunk(repo):
    """The release commit R tagged and recorded, the event commit after it, the PR merged with a merge commit: HEAD is main at M."""
    _released_branch(repo)
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "-m", "Merge pull request #1 from release/v1.2.3", "release/v1.2.3")
    git(repo, "branch", "-D", "release/v1.2.3")  # gh pr merge --delete-branch
    return repo


@pytest.mark.parametrize("command", TAG_ONLY)
def test_a_push_that_sends_only_the_tag_is_judged_by_the_tag_after_the_merge(merged_trunk, command):
    assert run_hook(command, merged_trunk) is None


@pytest.mark.parametrize("command", WITH_THE_TRUNK)
def test_a_push_that_sends_the_trunk_is_still_judged_by_head_after_the_merge(merged_trunk, command):
    out = run_hook(command, merged_trunk)
    assert blocked(out) and "but HEAD is" in out["permissionDecisionReason"]  # the merge commit is no release commit


def test_the_combined_trunk_push_on_the_release_commit_is_allowed(repo):
    """The on-trunk release (``push-tag`` prints ``--atomic origin main refs/tags/vX``) keeps working: HEAD is the release commit."""
    _released_branch(repo)
    git(repo, "checkout", "main")
    git(repo, "merge", "--ff-only", "release/v1.2.3")
    assert run_hook(f"git push --atomic origin main refs/tags/v{VERSION}", repo) is None


def test_a_tag_only_push_of_a_tag_on_another_commit_is_still_denied(merged_trunk):
    git(merged_trunk, "tag", "-f", "-a", f"v{VERSION}", "-m", "moved")  # the tag now names the merge commit, not the verified one
    for command in (f"git push origin refs/tags/v{VERSION}", f"git push origin tag v{VERSION}", "git push --tags"):
        out = run_hook(command, merged_trunk)
        assert blocked(out) and f"the tag v{VERSION} is" in out["permissionDecisionReason"], command


@pytest.mark.parametrize(("command", "trunk"), [(f"git push origin refs/tags/v{VERSION}", False), (f"git push origin tag v{VERSION}", False),
                                                ("git push --tags", False), ("git push --follow-tags", True),
                                                (f"git push origin tag v{VERSION} main", True), (f"git push --atomic origin main refs/tags/v{VERSION}", True)])
def test_the_trunk_decision_per_form_on_the_trunk(merged_trunk, command, trunk):
    (action,) = find_actions(command)
    assert rg._is_trunk_push(merged_trunk, action) is trunk
    assert rg._judges_the_tag(merged_trunk, action) is (not trunk)


def test_tag_keyword_keeps_the_refspecs_after_it():
    (action,) = find_actions(f"git push origin tag v{VERSION} main")
    assert action.refs == ["main"] and action.tags and action.named_tags
    (action,) = find_actions("git push --follow-tags origin")
    assert action.tags and not action.named_tags and action.refs == []
    for rebuilt in (f"git push origin HEAD:refs/tags/v{VERSION}", f"git push origin refs/tags/v{VERSION} main:refs/tags/v9"):
        (action,) = find_actions(rebuilt)
        assert action.tags and not action.named_tags and action.refs == [], rebuilt
