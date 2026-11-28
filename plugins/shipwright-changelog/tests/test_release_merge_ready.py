"""Unit U4 (FINDINGS D110): ``release.py merge-ready`` decides the autonomous merge line and never merges.

In-process with an injected runner: the method follows the repository's settings (a merge commit preferred), the PR head is always
pinned, a squash or rebase merge onto a base that moved stops with a plain restart message, and every case that is not an autonomous
release on a feature branch is refused. The same scenarios on real git with the ``gh`` stub: ``test_release_merge_ready_e2e.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import release
from lib import release_commit, release_merge
from .test_release_cli import Fake
from .test_release_p4_cli import HEAD, VERSION, rec, seed

pytestmark = pytest.mark.covers("FR-01.09/AC16")

SKILL = Path(__file__).resolve().parents[1] / "skills" / "changelog" / "SKILL.md"
PR, BRANCH = "https://example.test/pr/1", "release/x"
ALL = {"mergeCommitAllowed": True, "squashMergeAllowed": True, "rebaseMergeAllowed": True}
SQUASH_ONLY = {**ALL, "mergeCommitAllowed": False, "rebaseMergeAllowed": False}


def autonomous(tmp_path: Path, **state) -> None:
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": HEAD, "tag": f"v{VERSION}", "checks_passed": []})
    seed(tmp_path, **{"mode": "standalone", "autonomy": "autonomous", "branch": BRANCH, "on_trunk": False, "pr_url": PR,
                      "base_branch": "main", **state})


def fake(settings: dict | None = None, *, behind: int = 0, **over) -> Fake:
    answers = {"merge-branch": {"stdout": BRANCH + "\n"}, "merge-head": {"stdout": HEAD + "\n"},
               "merge-pr-view": {"stdout": json.dumps({"state": "OPEN", "headRefOid": HEAD, "baseRefName": "main"})},
               "merge-settings": {"stdout": json.dumps(ALL if settings is None else settings)},
               "merge-remote-url": {"stdout": "bare\n"}, "merge-behind": {"exit": behind}}
    return Fake(**{**answers, **over})


def ask(tmp_path: Path, plugin_root: Path, runner: Fake):
    return release_merge.merge_ready(rec(tmp_path, runner), plugin_root, version=VERSION)


@pytest.mark.parametrize(("settings", "method"), [(ALL, "merge"), (SQUASH_ONLY, "squash"),
                                                  ({**ALL, "mergeCommitAllowed": False, "squashMergeAllowed": False}, "rebase"),
                                                  ({**ALL, "mergeCommitAllowed": False}, "squash")])
def test_the_method_follows_the_repository_settings_and_prefers_a_merge_commit(tmp_path, plugin_root, settings, method):
    autonomous(tmp_path)
    runner = fake(settings)
    code, out = ask(tmp_path, plugin_root, runner)
    assert code == 0 and out["status"] == "ok" and out["method"] == method, out
    assert out["argv"] == ["gh", "pr", "merge", f"--{method}", "--match-head-commit", HEAD, "--delete-branch"]
    assert out["line"] == " ".join(out["argv"]) and not any(argv[:3] == ["gh", "pr", "merge"] for _, argv in runner.calls)  # decides, never merges
    assert runner.argv("merge-settings")[-3:] == ["view", "--json", "mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed"]
    assert ("merge-fetch" in runner.keys()) is (method != "merge")  # only a squash or rebase merge asks whether the base moved


def test_a_squash_onto_a_base_that_moved_stops_with_a_plain_restart_message(tmp_path, plugin_root):
    autonomous(tmp_path)
    runner = fake(SQUASH_ONLY, behind=1)
    code, out = ask(tmp_path, plugin_root, runner)
    assert code == 1 and out["status"] == "refused" and out["reason"] == "base_moved" and "line" not in out and "argv" not in out
    assert out["detail"].startswith("Nothing was merged.") and "Restart the release by hand" in out["detail"] and f"git tag -d v{VERSION}" in out["detail"]
    assert runner.argv("merge-fetch")[-1] == "main" and runner.argv("merge-behind") == ["git", "merge-base", "--is-ancestor", "FETCH_HEAD", HEAD]


def test_a_merge_commit_does_not_wait_for_an_up_to_date_branch(tmp_path, plugin_root):
    """A merge commit keeps U3's path: commits merged next to it are not in the release's tree, their drops stay pending (D112 holds)."""
    autonomous(tmp_path)
    code, out = ask(tmp_path, plugin_root, fake(ALL, behind=1))
    assert code == 0 and out["method"] == "merge"


@pytest.mark.parametrize(("over", "reason"), [
    ({"merge-fetch": {"exit": 128, "stderr": "fatal: could not read"}}, "base_state_unknown"),
    ({"merge-behind": {"exit": 128}}, "base_state_unknown"),
    ({"merge-settings": {"exit": 1, "stdout": ""}}, "repo_settings_unknown"),
    ({"merge-settings": {"stdout": json.dumps({"mergeCommitAllowed": True})}}, "repo_settings_unknown"),
    ({"merge-settings": {"stdout": json.dumps({k: False for k in ALL})}}, "no_merge_method_allowed"),
    ({"merge-pr-view": {"stdout": json.dumps({"state": "OPEN", "headRefOid": "b" * 40, "baseRefName": "main"})}}, "pr_head_not_the_release"),
    ({"merge-pr-view": {"stdout": json.dumps({"state": "MERGED", "headRefOid": HEAD})}}, "pr_already_merged"),
    ({"merge-pr-view": {"stdout": json.dumps({"state": "OPEN", "headRefOid": HEAD, "baseRefName": "develop"})}}, "pr_base_changed"),
    ({"merge-pr-view": {"stdout": json.dumps({"state": "CLOSED", "headRefOid": HEAD})}}, "pr_closed_unmerged"),
    ({"merge-pr-view": {"exit": 1, "stdout": ""}}, "pr_state_unknown"),
    ({"merge-branch": {"stdout": "main\n"}}, "head_not_on_branch"),
    ({"merge-head": {"stdout": "c" * 40 + "\n"}, "merge-git": {"exit": 1}}, "head_moved_since_release"),
])
def test_every_case_without_a_safe_line_is_refused_with_its_own_reason(tmp_path, plugin_root, over, reason):
    autonomous(tmp_path)
    code, out = ask(tmp_path, plugin_root, fake(SQUASH_ONLY, **over))
    assert code == 1 and out["status"] == "refused" and out["reason"] == reason and out["detail"] and "line" not in out, out


@pytest.mark.parametrize(("state", "reason"), [({"autonomy": "guided"}, "merge_left_to_a_person"), ({"autonomy": None}, "merge_left_to_a_person"),
                                               ({"mode": "pipeline"}, "driven_run_never_merges"),
                                               ({"on_trunk": True, "branch": "main", "pr_url": ""}, "released_on_the_trunk"),
                                               ({"pr_url": ""}, "event_not_recorded")])
def test_only_an_autonomous_release_from_a_feature_branch_gets_a_line(tmp_path, plugin_root, state, reason):
    autonomous(tmp_path, **state)
    runner = fake()
    code, out = ask(tmp_path, plugin_root, runner)
    assert code == 1 and out["reason"] == reason and not any(k.startswith("merge-") for k in runner.keys()), out


def test_no_release_record_is_refused(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", autonomy="autonomous", branch=BRANCH, on_trunk=False, pr_url=PR)
    assert ask(tmp_path, plugin_root, fake())[1]["reason"] == "release_not_committed"


def test_the_answer_never_carries_the_user_and_token_of_the_push_url(tmp_path, plugin_root):
    autonomous(tmp_path)
    code, out = ask(tmp_path, plugin_root, fake(SQUASH_ONLY, **{"merge-remote-url": {"stdout": "https://x-access-token:s3cr3t@github.com/o/r.git\n"}}))
    assert code == 0 and "s3cr3t" not in json.dumps(out) and "***@github.com" in json.dumps(out)


@pytest.mark.parametrize("settings", [ALL, SQUASH_ONLY])
def test_the_skill_carries_the_one_literal_merge_line_merge_ready_prints(tmp_path, plugin_root, settings):
    """The guard sees the merge as one literal line in SKILL.md (BRIEF section 2); the printed line is that template filled in."""
    skill = " ".join(SKILL.read_text(encoding="utf-8").split())
    template = "gh pr merge --{method} --match-head-commit {head} --delete-branch"
    assert template in skill and 'release.py" merge-ready' in skill
    assert skill.count("gh pr merge") == 1  # no second merge line (the old unpinned --merge line is gone)
    autonomous(tmp_path)
    out = ask(tmp_path, plugin_root, fake(settings))[1]
    assert out["line"] == template.replace("{method}", out["method"]).replace("{head}", HEAD)


def test_the_cli_answers_merge_ready_as_json(tmp_path, capsys):
    autonomous(tmp_path)
    code = release.main(["merge-ready", "--project-root", str(tmp_path), "--version", f"v{VERSION}"], runner=fake(SQUASH_ONLY))
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "ok" and out["method"] == "squash"
