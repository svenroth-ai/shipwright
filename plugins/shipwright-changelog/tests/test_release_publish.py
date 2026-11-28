"""U3 (D110 part 2, D112): ``release_publish.publish`` in process, on real git with a bare remote.

The end-to-end tests drive the same code through ``release.py push-tag`` in a subprocess; these call it directly, one case per
answer: a squash, a rebase and a merge commit are proven and retagged, every refusal writes nothing and moves no tag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib import release_commit, release_publish
from lib.release_runner import Recorder, subprocess_runner

from .test_release_guard import VERSION, git, repo as _repo

repo = _repo  # the fixture, re-exported so pytest finds it in this module
pytestmark = pytest.mark.covers("FR-01.09/AC11")
TAG = f"v{VERSION}"


def _commit(work: Path, name: str, text: str, message: str) -> str:
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(work, "add", name)
    git(work, "commit", "-q", "-m", message)
    return git(work, "rev-parse", "HEAD")


def _tree_commit(work: Path, of: str, *parents: str, message: str = "Release (#1)") -> str:
    return git(work, "commit-tree", f"{of}^{{tree}}", *[a for p in parents for a in ("-p", p)], "-m", message)


@pytest.fixture
def release(repo):
    """R on a release branch, the event commit H on top, the tag on R, the record naming R: push-tag's start after the merge."""
    base = git(repo, "rev-parse", "main")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "release/next")
    r = _commit(repo, "CHANGELOG.md", "# Changelog\n\n## [1.2.3]\n", "chore(release): v1.2.3")
    h = _commit(repo, ".shipwright/events/drops/e.jsonl", "{}\n", "chore(changelog): record the release event")
    git(repo, "tag", "-a", "-m", f"Release {TAG}", TAG, r)
    record = {"schema": 1, "version": VERSION, "tag": TAG, "commit": r, "checks_passed": ["commit"]}
    release_commit.write_state(repo, record)
    return {"repo": repo, "base": base, "R": r, "H": h, "record": record}


def _land(m: dict, merged: str) -> str:
    git(m["repo"], "push", "-q", "origin", f"{merged}:refs/heads/main")
    return merged


def _publish(m: dict, merged: str, **view) -> tuple[str, dict]:
    rec = Recorder(subprocess_runner, m["repo"])
    shown = {"headRefOid": m["H"], "mergeCommit": {"oid": merged}, "baseRefName": "main", **view}
    return release_publish.publish(rec, release_commit.read_state(m["repo"]), tag=TAG, base_branch="main", view=shown)


def _tag(m: dict) -> str:
    return git(m["repo"], "rev-parse", f"refs/tags/{TAG}^{{commit}}")


def test_a_squash_is_proven_written_and_retagged_and_a_re_run_changes_nothing(release):
    s = _land(release, _tree_commit(release["repo"], release["H"], release["base"]))
    reason, fields = _publish(release, s)
    assert reason == "ok" and fields["merged_via"] == "squash" and fields["retagged"], fields
    record = release_commit.read_state(release["repo"])
    assert record["published_commit"] == s and record["proof"]["base_before"] == release["base"] and _tag(release) == s
    assert _publish(release, s) == ("ok", {**fields, "retagged": False}) and release_commit.read_state(release["repo"]) == record


def test_a_rebase_is_proven_as_a_rebase(release):
    work = release["repo"]
    replayed = _tree_commit(work, release["R"], release["base"], message="chore(release): v1.2.3 (rebased)")
    s = _land(release, _tree_commit(work, release["H"], replayed, message="chore(changelog): record the release event (rebased)"))
    reason, fields = _publish(release, s)
    assert reason == "ok" and fields["merged_via"] == "rebase" and _tag(release) == s, fields


def test_a_merge_commit_is_proven_as_a_merge(release):
    s = _land(release, _tree_commit(release["repo"], release["H"], release["base"], release["H"]))
    reason, fields = _publish(release, s)
    assert reason == "ok" and fields["merged_via"] == "merge", fields


@pytest.mark.parametrize("drop", [True, False])
def test_a_foreign_commit_stops_it_naming_the_commit_and_its_drop(release, drop):
    work = release["repo"]
    git(work, "checkout", "-q", "-b", "other", release["base"])
    name = "CHANGELOG-unreleased.d/Added/other_001.md" if drop else "other.txt"
    foreign = _commit(work, name, "- another change\n", "feat: another PR\x1b[31m merged first")
    git(work, "merge", "-q", "--squash", release["H"])
    git(work, "commit", "-q", "-m", "Release (#1)")
    s = _land(release, git(work, "rev-parse", "HEAD"))
    before = release_commit.read_state(work)
    reason, fields = _publish(release, s)
    assert reason == "foreign_commits_on_base" and [c["commit"] for c in fields["foreign_commits"]] == [foreign], fields
    assert fields["foreign_commits"][0]["drops"] == ([name] if drop else []) and "\x1b" not in fields["foreign_commits"][0]["subject"]
    assert ("none of them added a changelog drop" in fields["detail"]) is not drop
    assert release_commit.read_state(work) == before and _tag(release) == release["R"]


def test_a_merge_commit_of_another_shape_is_refused_with_the_shape_named(release):
    work = release["repo"]
    side = _tree_commit(work, release["base"], release["base"], message="side")
    s = _land(release, _tree_commit(work, release["H"], release["base"], side))  # two parents, the second not the PR head
    reason, fields = _publish(release, s)
    assert reason == "foreign_commits_on_base" and "not a squash, merge or rebase" in fields["detail"], fields


def test_every_refusal_writes_nothing_and_moves_no_tag(release, tmp_path):
    work = release["repo"]
    s = _tree_commit(work, release["H"], release["base"])
    before = release_commit.read_state(work)
    assert _publish(release, s, headRefOid=None)[0] == "merge_commit_unknown"
    assert _publish(release, s, baseRefName="develop")[0] == "pr_base_changed"
    assert _publish(release, s, headRefOid=release["base"])[0] == "pr_head_not_the_release"
    assert _publish(release, s)[0] == "merge_commit_not_on_base"  # S never reached origin's main
    _land(release, s)
    git(work, "push", "-q", "origin", f"refs/tags/{TAG}")  # the tag on R is already out
    reason, fields = _publish(release, s)
    assert reason == "tag_on_origin_not_the_merge_commit" and fields["tag_commit"] == release["R"], fields
    git(work, "remote", "set-url", "--push", "origin", (tmp_path / "gone.git").as_posix())
    assert _publish(release, s)[0] == "merge_state_unknown"
    assert release_commit.read_state(work) == before and _tag(release) == release["R"]


def test_a_record_naming_another_merge_commit_is_refused(release):
    s = _land(release, _tree_commit(release["repo"], release["H"], release["base"]))
    release_commit.write_state(release["repo"], {**release["record"], "published_commit": "a" * 40, "merged_via": "squash",
                                                 "proof": {"pr_head": release["H"], "tree": "b" * 40, "base_before": release["base"]}})
    reason, fields = _publish(release, s)
    assert reason == "merge_commit_changed" and fields["recorded"] == "a" * 40, fields


def test_a_tag_on_origin_already_on_the_merge_commit_is_fetched_as_it_is(release):
    work = release["repo"]
    s = _land(release, _tree_commit(work, release["H"], release["base"]))
    git(work, "tag", "-f", "-a", "-m", "made on the host", TAG, s)
    git(work, "push", "-q", "origin", f"refs/tags/{TAG}")
    remote = git(work, "rev-parse", f"refs/tags/{TAG}")
    git(work, "tag", "-f", "-a", "-m", f"Release {TAG}", TAG, release["R"])  # the local tag still names R
    reason, fields = _publish(release, s)
    assert reason == "ok" and not fields["retagged"] and git(work, "rev-parse", f"refs/tags/{TAG}") == remote, fields
