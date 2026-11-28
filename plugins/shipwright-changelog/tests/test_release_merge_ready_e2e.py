"""U4 (FINDINGS D110) end to end: an autonomous release on real git with a bare remote and the ``gh`` stub asks ``release.py merge-ready``
which merge to run, the release guard allows that line, and the line really merges through the stub.

A repository that allows only squash merges gets a squash line pinned with ``--match-head-commit`` (push-tag then proves the merge, U3);
one that allows merge commits gets ``--merge`` (the tag stays on the release commit). A base that moved stops before a squash with a
plain restart message, and nothing is merged. A commit pushed to the branch after the answer makes the host refuse the pinned line.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from lib import release_commit

from .golden import conftest as golden  # first: it puts the testkit on the path
from .golden import scenario_support as ss  # noqa: I001
from .golden.driver_cli import CliDriver
from .golden.scenario_core import release_flow
from .test_release_push_merge_e2e import _foreign_commit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "hooks"))
import release_guard as rg  # noqa: E402

make_project, make_scratch, warm_uv = golden.make_project, golden.make_scratch, golden.warm_uv  # the harness fixtures, re-exported
pytestmark = pytest.mark.covers("FR-01.09/AC16")
VERSION, TAG = "1.3.0", "v1.3.0"
SQUASH_ONLY = {"mergeCommitAllowed": False, "squashMergeAllowed": True, "rebaseMergeAllowed": False}


def _gh(s, *args: str):
    return s.run([*json.loads(s.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"]), *args])


def _repo_settings(s, settings: dict) -> None:
    """What ``gh repo view`` reports: the stub reads the repository's merge settings from its state (all allowed when unset)."""
    path = s.stub_state / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["repo"] = settings
    path.write_text(json.dumps(state), encoding="utf-8")


def _ask_and_merge(s, driver, seen: dict, monkeypatch, settings: dict | None, *, foreign: bool = False, run_line: bool = True):
    """Just before the driver's own ``merge-pr``: (a foreign commit lands,) ``merge-ready`` answers, the guard judges the printed line, it runs."""
    def hook() -> None:
        s.git("push", "-q", "origin", "main")  # the scratch's history on main reaches origin, as a real base would be
        if settings is not None:
            _repo_settings(s, settings)
        if foreign:
            seen["F"] = _foreign_commit(s)
        for key, value in s.env.items():  # the hook runs in this process: give it the scratch's git environment
            monkeypatch.setenv(key, value)
        seen["H"] = s.git("rev-parse", "HEAD")
        seen["code"], seen["out"] = driver._release(s, "merge-ready", "--version", VERSION)
        line = seen["out"].get("line")
        seen["guarded"] = rg._active_state(s.repo) is not None  # a release is in progress: the guard is not inert
        seen["guard"] = rg.decide(line, s.repo) if line else "no line"
        if line and run_line:
            seen["merged"] = _gh(s, *shlex.split(line)[1:])
    return hook


def _flow(make_project, monkeypatch, settings: dict | None, **kw) -> tuple:
    s = ss.ready_release(make_project, autonomy="autonomous")
    driver, seen = CliDriver(), {}
    results = release_flow(driver, s, "autonomous", before={"merge-pr": _ask_and_merge(s, driver, seen, monkeypatch, settings, **kw)})
    assert results[-1].step == "merge-pr" and results[-1].exit_code != 0, [(r.step, r.exit_code) for r in results]  # merged already, or refused
    return s, driver, seen


def _out(seen: dict) -> dict:
    return {k: v for k, v in seen["out"].items() if k != "commands"}


@pytest.mark.covers("FR-01.09/AC11")
def test_a_squash_only_repo_gets_a_pinned_squash_line_the_guard_allows_and_push_tag_proves(make_project, monkeypatch):
    s, driver, seen = _flow(make_project, monkeypatch, SQUASH_ONLY)
    out = _out(seen)
    assert seen["code"] == 0 and out["method"] == "squash" and out["head"] == seen["H"], out
    assert out["line"] == f"gh pr merge --squash --match-head-commit {seen['H']} --delete-branch"
    assert seen["guarded"] and seen["guard"] is None  # the release guard, active, allows the chosen line during the release
    assert seen["merged"].returncode == 0, seen["merged"].stderr
    pr = s.gh_state()["prs"][0]
    assert pr["state"] == "merged" and pr["head_oid"] == seen["H"]
    assert [c["argv"][:3] for c in s.gh_argv_log() if c["argv"][:2] == ["pr", "merge"]][0] == ["pr", "merge", "--squash"]
    code, pushed = driver._release(s, "push-tag", "--version", VERSION)  # U3 proves the squash merge commit
    assert code == 0 and pushed["merged_via"] == "squash" and pushed["line"] == f"git push origin refs/tags/{TAG}", pushed.get("reason")


def test_a_repo_that_allows_merge_commits_gets_a_pinned_merge_line_and_the_tag_stays_on_the_release(make_project, monkeypatch):
    s, driver, seen = _flow(make_project, monkeypatch, None)  # unset: GitHub's default, all three allowed
    out = _out(seen)
    assert seen["code"] == 0 and out["line"] == f"gh pr merge --merge --match-head-commit {seen['H']} --delete-branch", out
    assert seen["guard"] is None and seen["merged"].returncode == 0, seen["merged"].stderr
    code, pushed = driver._release(s, "push-tag", "--version", VERSION)
    record = release_commit.read_state(s.repo)
    assert code == 0 and "published_commit" not in record and s.git("rev-parse", f"{TAG}^{{commit}}") == record["commit"], pushed.get("reason")


def test_a_base_that_moved_stops_before_a_squash_with_a_restart_message_and_nothing_is_merged(make_project, monkeypatch):
    s, driver, seen = _flow(make_project, monkeypatch, SQUASH_ONLY, foreign=True)
    out = _out(seen)
    assert seen["code"] == 1 and out["status"] == "refused" and out["reason"] == "base_moved" and "line" not in out, out
    assert out["detail"].startswith("Nothing was merged.") and "Restart the release by hand" in out["detail"]
    main = s.git("ls-remote", s.origin.as_posix(), "refs/heads/main").split("\t")[0]
    assert main == seen["F"] and s.gh_state()["prs"][0]["state"] == "open"  # origin's main holds only the foreign commit; the PR is open
    assert all(c["exit"] != 0 for c in s.gh_argv_log() if c["argv"][:2] == ["pr", "merge"])  # the driver's unpinned --merge was refused too


def test_a_commit_pushed_to_the_branch_after_the_answer_makes_the_host_refuse_the_pinned_line(make_project, monkeypatch):
    s, driver, seen = _flow(make_project, monkeypatch, SQUASH_ONLY, run_line=False)
    assert seen["code"] == 0 and seen["guard"] is None
    ss.commit(s, "late.txt", "pushed after the release\n", "fix: pushed after the release")
    s.git("push", "-q", "origin", "HEAD")
    late = _gh(s, *shlex.split(seen["out"]["line"])[1:])
    assert late.returncode != 0 and "Head branch was modified" in late.stderr
    assert s.gh_state()["prs"][0]["state"] == "open"
    assert rg.decide(seen["out"]["line"], s.repo) is not None  # the guard denies it too: HEAD is no longer the release
