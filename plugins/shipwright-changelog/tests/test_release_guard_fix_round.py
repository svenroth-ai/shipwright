"""Fix round of unit P4b after the independent opus reviews: the tag push that follows the merge, event-only history, unknown
directories, UTF-8 input (real git; each case fails on the first version of the hook)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from lib import release_event

from .test_release_guard import HOOK, VERSION, blocked, git, record, repo as _repo, run_hook, start_release
from .test_release_guard_review_fixes import _patch_state

repo = _repo  # the fixture, re-exported so pytest finds it in this module
pytestmark = pytest.mark.covers("FR-01.09/AC01")


def _event_commit(work):
    (work / ".shipwright/events/drops").mkdir(parents=True, exist_ok=True)
    (work / ".shipwright/events/drops/e1.jsonl").write_text("{}\n", encoding="utf-8")
    git(work, "add", ".shipwright/events/drops")
    git(work, "commit", "-m", "chore(release): record changelog event")


def _released_branch(work):
    """The state SKILL.md Step 7 reaches: release commit R tagged, record names R, event commit E on the release branch."""
    git(work, "checkout", "-b", "release/v1.2.3")
    (work / "CHANGELOG.md").write_text("# v1.2.3\n", encoding="utf-8")
    git(work, "add", "CHANGELOG.md")
    git(work, "commit", "-m", "chore(release): v1.2.3")
    release = git(work, "rev-parse", "HEAD")
    git(work, "tag", "-a", f"v{VERSION}", "-m", "Release", release)
    start_release(work)
    record(work)
    _event_commit(work)
    return release


def test_the_tag_push_after_a_no_ff_merge_is_allowed(repo):
    """Old hook judged HEAD (the merge commit on main) and denied the push SKILL.md Step 7 prescribes after `gh pr merge`."""
    _released_branch(repo)
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "-m", "Merge release", "release/v1.2.3")
    assert run_hook(f"git push origin v{VERSION}", repo) is None
    assert run_hook(f"gh release create v{VERSION} --verify-tag", repo) is None
    assert blocked(run_hook("git push origin main", repo))  # a trunk push still judges HEAD (a merge commit is no release commit)


def test_the_tag_push_after_a_squash_merge_is_allowed(repo):
    """The squash commit is not a descendant of the release commit; the tag still names it."""
    _released_branch(repo)
    git(repo, "checkout", "main")
    git(repo, "merge", "--squash", "release/v1.2.3")
    git(repo, "commit", "-m", "Release v1.2.3 (squash)")
    assert subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", git(repo, "rev-parse", f"v{VERSION}^{{commit}}"), "HEAD"]).returncode != 0
    assert run_hook(f"git push origin v{VERSION}", repo) is None


def test_a_tag_on_another_commit_is_denied_and_the_advice_fits(repo):
    release = _released_branch(repo)
    git(repo, "checkout", "main")
    git(repo, "tag", "-f", f"v{VERSION}")  # the tag now names main's tip, not the verified release commit
    out = run_hook(f"git push origin v{VERSION}", repo)
    assert blocked(out)
    reason = out["permissionDecisionReason"]
    assert release[:10] in reason and "the tag v1.2.3 is" in reason and "does not exist" not in reason


def test_an_already_tagged_release_without_a_record_says_to_run_commit_and_tag(repo):
    start_release(repo)
    out = run_hook("git push --tags origin main", repo)
    assert "does not exist yet; run `release.py commit-and-tag`" in out["permissionDecisionReason"]


def test_an_empty_commit_is_not_an_event_commit(repo):
    start_release(repo)
    record(repo)
    git(repo, "commit", "--allow-empty", "-m", "nothing")
    assert blocked(run_hook("git push origin main", repo))


def test_a_rename_into_the_events_folder_is_not_an_event_commit(repo):
    start_release(repo)
    record(repo)
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    git(repo, "mv", "a.txt", ".shipwright/events/drops/a.jsonl")  # the deleted side is a.txt: a code path
    git(repo, "commit", "-m", "move")
    assert blocked(run_hook("git push origin main", repo))


def test_before_record_event_a_merge_naming_a_pr_is_held(repo):
    start_release(repo)  # no branch, no pr_url in the state yet
    assert blocked(run_hook("gh pr merge 42 --merge", repo))


@pytest.mark.parametrize("prefix", ["popd && ", "Pop-Location; ", "cd $dir && ", "cd $(git rev-parse --show-toplevel) && "])
def test_an_unknown_directory_fails_open(repo, prefix):
    start_release(repo)
    assert run_hook(prefix + "git push origin main", repo) is None


def test_a_non_ascii_cwd_and_payload_are_read_as_utf8(tmp_path, repo):
    start_release(repo)
    odd = repo / "résumé-日本"
    odd.mkdir()
    body = {"tool_name": "Bash", "tool_input": {"command": "git push --tags origin main  # ü"}, "cwd": str(odd)}
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(body, ensure_ascii=False).encode("utf-8"), capture_output=True)
    assert done.returncode == 0 and b"deny" in done.stdout


def test_the_hooks_trunks_cover_the_release_clis():
    sys.path.insert(0, str(HOOK.parent))
    import release_guard  # noqa: PLC0415
    assert set(release_event.TRUNKS) <= set(release_guard.TRUNKS)  # the hook also guards `master`, which record-event does not name


def test_a_tag_push_check_is_made_after_the_state_check(repo, monkeypatch):
    """No release running: the hook must answer without classifying the push (no show-ref / rev-parse of HEAD)."""
    sys.path.insert(0, str(HOOK.parent))
    import release_guard  # noqa: PLC0415
    calls = []
    real = release_guard._git
    monkeypatch.setattr(release_guard, "_git", lambda cwd, *a, **k: (calls.append(a[0]), real(cwd, *a, **k))[1])
    assert release_guard.decide("git push origin v1.2.3", repo) is None
    assert calls == ["rev-parse"]  # only the run-state path lookup
    _patch_state  # imported for the other fix-round module; keeps the helper reachable from here
