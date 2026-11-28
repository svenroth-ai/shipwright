"""U3 (D110 part 2, D112) end to end: a whole autonomous release on real git with a bare remote and the ``gh`` stub, merged by squash,
by rebase or with a merge commit, then ``release.py push-tag``, the tag push through the release guard and ``close-phase``.

The stub merges the PR itself and reports the merge commit (FINDINGS D114). After a squash or rebase merge ``push-tag`` proves the merge
commit, writes the proof into the release record and moves the local tag onto it; the guard then allows the push and the closing verify
passes 8 of 8. A merge commit keeps the tag on the release commit. A foreign commit merged onto the base before the squash ends in
``foreign_commits_on_base``, naming it and its drop, and nothing is tagged or written. A re-run gives the same answer, and a tag
already on origin is never moved.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lib import release_commit

from .golden import conftest as golden  # first: it puts the testkit on the path
from .golden import scenario_support as ss  # noqa: I001
from .golden.driver_cli import CliDriver
from .golden.scenario_core import release_flow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "hooks"))
import release_guard as rg  # noqa: E402

make_project, make_scratch, warm_uv = golden.make_project, golden.make_scratch, golden.warm_uv  # the harness fixtures, re-exported
pytestmark = pytest.mark.covers("FR-01.09/AC01")
VERSION, TAG = "1.3.0", "v1.3.0"
PUSH = f"git push origin refs/tags/{TAG}"
FOREIGN_DROP_RUN = "iterate-2026-11-27-foreign"


def _gh(s, *args: str):
    return s.run([*json.loads(s.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"]), *args])


def _foreign_commit(s) -> str:
    """Another PR lands on origin's main while the release PR is open: a code change with its own pending changelog drop."""
    branch = s.git("rev-parse", "--abbrev-ref", "HEAD")
    s.git("fetch", "-q", s.origin.as_posix(), "main")
    s.git("checkout", "-q", "-b", "other-pr", "FETCH_HEAD")
    (s.repo / "other.txt").write_text("landed next to the release\n", encoding="utf-8")
    s.git("add", "other.txt")
    ss.write_drop(s, "Added", "Another change that needs its own entry", run_id=FOREIGN_DROP_RUN)
    s.git("add", "--", "CHANGELOG-unreleased.d")
    s.git("commit", "-q", "-m", "feat: another PR merged first")
    foreign = s.git("rev-parse", "HEAD")
    s.git("push", "-q", "origin", "other-pr:main")
    s.git("checkout", "-q", branch)
    return foreign


def _merge_by(s, method: str, seen: dict, *, foreign: bool = False):
    """Before ``merge-pr``: (a foreign commit lands, then) the stub merges the PR with ``method``; the driver's own merge then finds no open PR."""
    def hook() -> None:
        s.git("push", "-q", "origin", "main")  # the scratch's history on main reaches origin, as a real base would be
        if foreign:
            seen["F"] = _foreign_commit(s)
        seen["H"] = s.git("rev-parse", "HEAD")
        done = _gh(s, "pr", "merge", method, "--delete-branch")
        assert done.returncode == 0, done.stderr
        seen["S"] = s.gh_state()["prs"][0]["merge_commit"]
    return hook


def _merged_release(make_project, method: str, *, foreign: bool = False) -> tuple:
    s = ss.ready_release(make_project, autonomy="autonomous")
    driver, seen = CliDriver(), {}
    results = release_flow(driver, s, "autonomous", before={"merge-pr": _merge_by(s, method, seen, foreign=foreign)})
    assert results[-1].step == "merge-pr" and results[-1].exit_code != 0, [(r.step, r.exit_code) for r in results]  # merged already
    return s, driver, seen


def _push_tag(driver, s) -> tuple[int, dict]:
    code, out = driver._release(s, "push-tag", "--version", VERSION)
    return code, {k: v for k, v in out.items() if k != "commands"}


def _close(driver, s) -> tuple[int, dict]:
    return driver._release(s, "close-phase", "--version", VERSION, "--release-status", "skipped", "--release-note", "no page in this test")


def _origin_tag(s) -> str:
    return s.git("ls-remote", s.origin.as_posix(), f"refs/tags/{TAG}^{{}}").split("\t")[0]


@pytest.mark.covers("FR-01.09/AC11")
@pytest.mark.parametrize(("method", "via"), [("--squash", "squash"), ("--rebase", "rebase")])
def test_a_squash_or_rebase_merged_release_is_proven_retagged_pushed_through_the_guard_and_closes_8_of_8(make_project, monkeypatch, method, via):
    s, driver, seen = _merged_release(make_project, method)
    for key, value in s.env.items():  # the hook runs in this process: give it the scratch's git environment
        monkeypatch.setenv(key, value)
    release = release_commit.read_state(s.repo)["commit"]
    assert s.git("rev-parse", f"{TAG}^{{commit}}") == release and seen["S"] != release  # before: the tag names R, which is off the base
    code, out = _push_tag(driver, s)
    assert code == 0 and out["status"] == "ok" and out["line"] == PUSH and out["merged_via"] == via and out["retagged"], out
    record = release_commit.read_state(s.repo)
    assert record["commit"] == release and record["published_commit"] == seen["S"] and record["merged_via"] == via
    assert record["proof"]["pr_head"] == seen["H"] and s.git("rev-parse", f"{TAG}^{{commit}}") == seen["S"]
    assert release[:40] in s.git("tag", "-l", "--format=%(contents)", TAG)  # the moved tag's message names the release commit
    assert rg.decide(PUSH, s.repo) is None  # the guard allows the push of the tag on S
    s.git("push", "-q", "origin", f"refs/tags/{TAG}")
    code, closed = _close(driver, s)
    assert code == 0 and closed["status"] == "ok", [c for c in closed.get("verify", []) if not c["ok"]] or closed
    assert len(closed["verify"]) == 8 and all(c["ok"] for c in closed["verify"]), closed["verify"]
    again = _push_tag(driver, s)  # a re-run after the push: the same answer, nothing moves
    assert again[0] == 0 and again[1]["line"] == PUSH and not again[1]["retagged"] and _origin_tag(s) == seen["S"]
    assert release_commit.read_state(s.repo) == record


def test_a_re_run_before_the_tag_push_gives_the_same_answer(make_project):
    s, driver, seen = _merged_release(make_project, "--squash")
    first = _push_tag(driver, s)
    record = release_commit.read_state(s.repo)
    second = _push_tag(driver, s)
    assert first[0] == second[0] == 0 and second[1]["line"] == first[1]["line"] and not second[1]["retagged"]
    assert release_commit.read_state(s.repo) == record and s.git("rev-parse", f"{TAG}^{{commit}}") == seen["S"]


def test_a_merge_commit_keeps_the_tag_on_the_release_commit_and_closes_8_of_8(make_project, monkeypatch):
    s = ss.ready_release(make_project, autonomy="autonomous")
    driver, guarded = CliDriver(), []
    for key, value in s.env.items():  # the hook runs in this process: give it the scratch's git environment
        monkeypatch.setenv(key, value)

    def guard() -> None:  # just before the printed push runs: the guard allows the tag on R
        guarded.append(rg.decide(PUSH, s.repo))

    results = release_flow(driver, s, "autonomous", release_page=False, close=False, before={"push-tags": guard})
    assert all(r.exit_code == 0 for r in results), [(r.step, r.exit_code) for r in results]
    assert guarded == [None], guarded
    record = release_commit.read_state(s.repo)
    assert "published_commit" not in record and _origin_tag(s) == record["commit"]  # today's path: the tag on R
    code, closed = _close(driver, s)
    assert code == 0 and len(closed["verify"]) == 8 and all(c["ok"] for c in closed["verify"]), closed["verify"]


def test_a_foreign_commit_merged_before_the_squash_stops_naming_it_and_its_drop(make_project):
    s, driver, seen = _merged_release(make_project, "--squash", foreign=True)
    record_before = (s.repo / release_commit.RELEASE_STATE).read_bytes()
    tag_before = s.git("rev-parse", f"{TAG}^{{commit}}")
    for _ in range(2):  # a re-run gives the same answer
        code, out = _push_tag(driver, s)
        assert code == 1 and out["status"] == "refused" and out["reason"] == "foreign_commits_on_base", out
        (found,) = out["foreign_commits"]
        assert found["commit"] == seen["F"] and found["subject"] == "feat: another PR merged first"
        assert len(found["drops"]) == 1 and FOREIGN_DROP_RUN in found["drops"][0] and found["drops"][0].startswith("CHANGELOG-unreleased.d/")
        assert seen["F"][:10] in out["detail"] and "line" not in out
        assert (s.repo / release_commit.RELEASE_STATE).read_bytes() == record_before and s.git("rev-parse", f"{TAG}^{{commit}}") == tag_before
    assert _origin_tag(s) == ""  # nothing was pushed


def test_a_tag_already_on_origin_is_never_moved(make_project):
    s, driver, seen = _merged_release(make_project, "--squash")
    release = release_commit.read_state(s.repo)["commit"]
    s.git("push", "-q", "origin", f"refs/tags/{TAG}")  # the tag on R went out by hand before push-tag ran
    code, out = _push_tag(driver, s)
    assert code == 1 and out["reason"] == "tag_on_origin_not_the_merge_commit" and out["tag_commit"] == release, out
    assert _origin_tag(s) == release and s.git("rev-parse", f"{TAG}^{{commit}}") == release
    assert "published_commit" not in release_commit.read_state(s.repo)


def test_a_record_that_already_names_another_merge_commit_is_refused_and_left_alone(make_project):
    s, driver, seen = _merged_release(make_project, "--squash")
    record = release_commit.read_state(s.repo)
    record.update(published_commit=seen["H"], merged_via="squash", proof={"pr_head": seen["H"], "tree": "a" * 40, "base_before": "b" * 40})
    release_commit.write_state(s.repo, record)
    before = (s.repo / release_commit.RELEASE_STATE).read_bytes()
    code, out = _push_tag(driver, s)
    assert code == 1 and out["reason"] == "merge_commit_changed" and out["recorded"] == seen["H"], out
    assert (s.repo / release_commit.RELEASE_STATE).read_bytes() == before and s.git("rev-parse", f"{TAG}^{{commit}}") == record["commit"]


def _tamper_stub(s, **fields) -> None:
    """What gh reports about the merged PR, set by hand (the stub reports what it merged)."""
    path = s.stub_state / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    state["prs"][0].update(fields)
    path.write_text(json.dumps(state), encoding="utf-8")


@pytest.mark.parametrize("case", ["head_moved", "merge_off_base"])
def test_a_pr_head_past_the_release_or_a_merge_commit_off_the_base_is_refused_and_writes_nothing(make_project, case):
    s, driver, seen = _merged_release(make_project, "--squash")
    if case == "head_moved":  # a commit pushed to the branch after record-event
        extra = s.git("commit-tree", f"{seen['H']}^{{tree}}", "-p", seen["H"], "-m", "fix: pushed after the release")
        _tamper_stub(s, head_oid=extra)
        reason = "pr_head_not_the_release"
    else:  # gh names a merge commit the fetched base does not hold (the base was force-pushed past it)
        _tamper_stub(s, merge_commit=s.git("commit-tree", f"{seen['H']}^{{tree}}", "-p", seen["S"] + "^", "-m", "a squash not on main"))
        reason = "merge_commit_not_on_base"
    before = (s.repo / release_commit.RELEASE_STATE).read_bytes()
    tag = s.git("rev-parse", f"{TAG}^{{commit}}")
    for _ in range(2):
        code, out = _push_tag(driver, s)
        assert code == 1 and out["reason"] == reason, out
        assert (s.repo / release_commit.RELEASE_STATE).read_bytes() == before and s.git("rev-parse", f"{TAG}^{{commit}}") == tag


def test_the_answer_never_carries_the_user_and_token_of_a_remote_url(tmp_path):
    from lib import release_publish
    from lib.release_runner import CmdResult, Recorder

    def runner(key, argv, cwd, **_):
        return CmdResult(key, tuple(argv), 128 if argv[1] == "-c" else 0,
                         "https://x-access-token:s3cr3t@github.com/o/r.git\n" if "get-url" in argv else "", "fatal: https://u:p@h/x denied")

    rec = Recorder(runner, tmp_path)
    assert release_publish._remote(rec, ["ls-remote", "--tags"], ["refs/tags/v1"])[0] == 128
    text = json.dumps(rec.as_json())
    assert "s3cr3t" not in text and "u:p@" not in text and "***@github.com" in text
    assert rec.results[-1].argv[:3] == ("git", "-c", "credential.interactive=never")


def test_a_tag_on_origin_already_on_the_merge_commit_is_taken_as_it_is(make_project):
    s, driver, seen = _merged_release(make_project, "--squash")
    s.git("--git-dir", s.origin.as_posix(), "-c", "user.name=o", "-c", "user.email=o@x", "tag", "-a", TAG, "-m", "made on the host", seen["S"])
    remote_object = s.git("ls-remote", s.origin.as_posix(), f"refs/tags/{TAG}").split("\t")[0]
    code, out = _push_tag(driver, s)
    assert code == 0 and out["status"] == "ok" and not out["retagged"], out
    assert s.git("rev-parse", f"refs/tags/{TAG}") == remote_object  # the very tag object: the printed push is a no-op, not "already exists"
    assert s.run(["git", "push", "origin", f"refs/tags/{TAG}"]).returncode == 0


def test_a_pr_retargeted_to_another_base_is_refused(make_project):
    s, driver, seen = _merged_release(make_project, "--squash")
    _tamper_stub(s, base="develop")
    code, out = _push_tag(driver, s)
    assert code == 1 and out["reason"] == "pr_base_changed", out
    assert "published_commit" not in release_commit.read_state(s.repo)


def test_the_push_tag_answer_carries_no_user_or_token_of_the_push_url(make_project):
    """Code review of U3: the closing verify's fetch (on_base) reads the push URL too; the whole answer is redacted, not only publish's calls."""
    s, driver, _ = _merged_release(make_project, "--squash")
    s.git("remote", "set-url", "--push", "origin", "https://x-access-token:s3cr3t@127.0.0.1:9/o.git")
    code, out = driver._release(s, "push-tag", "--version", VERSION)
    text = json.dumps(out)
    assert code == 1 and out["reason"] == "merge_state_unknown", {k: v for k, v in out.items() if k != "commands"}
    assert "s3cr3t" not in text and "***@127.0.0.1" in text
