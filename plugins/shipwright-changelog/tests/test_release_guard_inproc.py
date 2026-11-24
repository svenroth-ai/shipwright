"""The release guard called in this process (unit P4b): the subprocess tests prove the hook end to end, but a subprocess is invisible to the
diff-coverage gate. These call the decision functions and ``main`` directly against real temporary git repositories; ``_git`` is
monkeypatched only for the paths a real repository cannot reach (a git that fails, a remote that cannot be asked)."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from .test_release_guard import VERSION, git, record, repo as _repo, start_release
from .test_release_guard_review_fixes import _patch_state

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "hooks"))
import release_guard as rg  # noqa: E402
from release_guard_commands import Action, find_actions  # noqa: E402

repo = _repo  # the fixture, re-exported so pytest finds it in this module
pytestmark = pytest.mark.covers("FR-01.09/AC01")


def _act(cmd: str) -> Action:
    (act,) = find_actions(cmd)
    return act


def test_effective_cwd_joins_parts_and_maps_git_bash_drive_paths(monkeypatch, tmp_path):
    assert rg._effective_cwd(tmp_path, _act("git -C sub push")) == tmp_path / "sub"
    monkeypatch.setattr(sys, "platform", "win32")
    assert rg._posix_drive("/c/Users/x") == "C:/Users/x" and rg._posix_drive("/d") == "D:/" and rg._posix_drive("rel/x") == "rel/x"
    monkeypatch.setattr(sys, "platform", "linux")
    assert rg._posix_drive("/c/Users/x") == "/c/Users/x"


def test_tag_and_trunk_classification(repo):
    git(repo, "tag", "shipped")
    assert rg._is_tag_push(repo, _act("git push --tags"))
    assert rg._is_tag_push(repo, _act("git push origin v1.2.3"))
    assert rg._is_tag_push(repo, _act("git push origin shipped"))  # an existing tag with no version shape
    assert not rg._is_tag_push(repo, _act("git push origin main HEAD feature"))
    assert rg._is_trunk_push(repo, _act("git push --all"))
    assert rg._is_trunk_push(repo, _act("git push origin HEAD:main"))
    assert rg._is_trunk_push(repo, _act("git push"))  # on main
    assert not rg._is_trunk_push(repo, _act("git push origin feature"))
    git(repo, "checkout", "-b", "feature")
    assert not rg._is_trunk_push(repo, _act("git push origin HEAD"))


def test_outward_and_tag_judging(repo):
    assert not rg._is_outward(repo, _act("gh -R o/r pr merge 3"))  # another repository
    assert not rg._is_outward(repo, _act("popd && git push origin main"))  # unknown directory
    assert rg._is_outward(repo, _act("gh pr merge")) and rg._is_outward(repo, _act("git push origin main"))
    assert not rg._is_outward(repo, _act("git push origin feature"))
    assert rg._judges_the_tag(repo, _act("gh release create v1")) and rg._judges_the_tag(repo, _act("git push origin v1.2.3"))
    assert not rg._judges_the_tag(repo, _act("git push origin main")) and not rg._judges_the_tag(repo, _act("gh pr merge"))


def test_release_merge_matching(repo):
    state = {"branch": "release/v1", "pr_url": "https://h/o/r/pull/9"}
    for cmd in ("gh pr merge 9", "gh pr merge release/v1", "gh pr merge https://h/o/r/pull/9"):
        assert rg._is_this_releases_merge(repo, _act(cmd), state)
    assert not rg._is_this_releases_merge(repo, _act("gh pr merge 8"), state)
    assert rg._is_this_releases_merge(repo, _act("gh pr merge 8"), {})  # nothing known yet: every merge counts
    assert not rg._is_this_releases_merge(repo, _act("gh pr merge"), state)  # current branch is main
    git(repo, "checkout", "-b", "release/v1")
    assert rg._is_this_releases_merge(repo, _act("gh pr merge"), state)
    assert rg._is_this_releases_merge(repo, _act("gh pr merge"), {})


def test_active_state_branches(repo, tmp_path):
    assert rg._active_state(repo) is None  # no state file
    assert rg._active_state(tmp_path) is None  # not a repository
    start_release(repo)
    assert rg._active_state(repo)["version"] == VERSION
    sub = repo / "pkg"
    sub.mkdir()
    assert rg._active_state(sub) is not None  # cwd inside the project root
    path = rg.Path(subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", rg.RUN_STATE_GIT_PATH], capture_output=True, text=True).stdout.strip())
    path = path if path.is_absolute() else repo / path
    base = json.loads(path.read_text(encoding="utf-8"))
    for bad in ({**base, "schema": 2}, {**base, "version": ""}, {**base, "created_at": "garbage"}, {**base, "project_root": ""},
                {**base, "created_at": "2020-01-01T00:00:00"}, {k: v for k, v in base.items() if k != "created_at"}):
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert rg._active_state(repo) is None
    naive = {**base, "created_at": rg.datetime.now(rg.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")}
    path.write_text(json.dumps(naive), encoding="utf-8")  # a naive timestamp is read as UTC
    assert rg._active_state(repo) is not None


def test_record_commit_reads(repo):
    assert rg._record_commit(repo, VERSION) is None
    record(repo)
    assert rg._record_commit(repo, VERSION) == git(repo, "rev-parse", "HEAD")
    assert rg._record_commit(repo, "9.9.9") is None
    (repo / rg.RECORD_REL).write_text("[1]", encoding="utf-8")
    assert rg._record_commit(repo, VERSION) is None


def test_event_only_descent_and_judged_commit(repo):
    release = git(repo, "rev-parse", "HEAD")
    assert rg._is_the_release(repo, release, release) and not rg._is_the_release(repo, release, "")
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops/e.jsonl").write_text("{}\n", encoding="utf-8")
    git(repo, "add", ".shipwright")
    git(repo, "commit", "-m", "event")
    assert rg._is_the_release(repo, release, git(repo, "rev-parse", "HEAD"))
    git(repo, "checkout", "-q", "-b", "side", release)
    (repo / "b.txt").write_text("b\n", encoding="utf-8")
    git(repo, "add", "b.txt")
    git(repo, "commit", "-m", "side")
    assert not rg._is_the_release(repo, git(repo, "rev-parse", "main"), git(repo, "rev-parse", "HEAD"))  # not a descendant
    git(repo, "merge", "--no-ff", "-m", "m", "main")
    assert not rg._is_the_release(repo, release, git(repo, "rev-parse", "HEAD"))  # a merge commit in between
    git(repo, "tag", f"v{VERSION}", release)
    assert rg._judged_commit(repo, VERSION, True) == release
    assert rg._judged_commit(repo, VERSION, False) == git(repo, "rev-parse", "HEAD")
    assert rg._judged_commit(repo, "7.7.7", True) == git(repo, "rev-parse", "HEAD")  # no tag yet: HEAD


def test_the_tag_lookup_paths(repo, monkeypatch):
    assert not rg._tag_is_on_origin(repo, VERSION)
    git(repo, "tag", f"v{VERSION}")
    git(repo, "push", "origin", f"v{VERSION}")
    assert rg._tag_is_on_origin(repo, VERSION)

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(rg, "_git", boom)
    assert not rg._tag_is_on_origin(repo, VERSION)  # a remote that cannot be asked keeps the deny


def test_decide_allows_denies_and_explains(repo):
    assert rg.decide("git push origin main", repo) is None  # no release
    start_release(repo)
    reason = rg.decide("git push origin main", repo)
    assert "does not exist yet; run `release.py commit-and-tag`" in reason and "gh release" not in reason
    assert "gh pr merge" in rg.decide("gh pr merge", repo) and "gh release create" in rg.decide("gh release create v1.2.3", repo)
    record(repo)
    assert rg.decide("git push origin main", repo) is None
    _patch_state(repo, branch="release/v1")
    assert rg.decide("gh pr merge 5", repo) is None  # another PR
    assert rg.decide("echo hi", repo) is None


def test_main_reads_stdin_and_prints_a_deny(repo, monkeypatch, capsys):
    start_release(repo)

    def feed(payload):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8"))))
        return rg.main()

    body = {"tool_name": "Bash", "tool_input": {"command": "git push --tags origin main"}, "cwd": str(repo)}
    assert feed(body) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert feed({**body, "tool_name": "Read"}) == 0 and capsys.readouterr().out == ""
    assert feed({**body, "tool_input": {"command": "  "}}) == 0 and capsys.readouterr().out == ""
    assert feed({**body, "cwd": None}) == 0  # falls back to the process directory
    assert feed(b"not json") == 0 and capsys.readouterr().out == ""
    monkeypatch.setenv("SHIPWRIGHT_RELEASE_GUARD", "off")
    assert feed(body) == 0 and capsys.readouterr().out == ""
    monkeypatch.delenv("SHIPWRIGHT_RELEASE_GUARD")
    monkeypatch.setattr(rg, "decide", lambda *a: 1 / 0)  # an error in the hook itself allows
    assert feed(body) == 0 and capsys.readouterr().out == ""


def test_parser_forms_not_reached_elsewhere():
    assert find_actions("FOO=1") == []  # nothing but an assignment
    assert _act("git -c user.name=x push origin main").refs == ["main"]
    assert _act("gh pr merge 3 --repo=o/r").foreign
    assert find_actions("popd; git push origin main")[0].cwd_unknown
    assert find_actions("cd $HOME && git push origin main")[0].cwd_unknown
