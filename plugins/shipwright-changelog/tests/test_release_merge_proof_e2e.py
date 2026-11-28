"""U2 (D110 part 1) end to end: a whole autonomous release on real git with a bare remote and the ``gh`` stub, squash-merged.

The stub merges with a merge commit only, so the squash is made by hand on the bare remote (S = a commit with the PR head's tree
on top of the base) and the stub's PR is marked merged. U3 will write the record fields and retag; until then this test writes
them the way the brief settles them. The guard then allows the tag push of S and close-phase passes 8 of 8; a record whose tree
does not match is denied by both.
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


def _squash_instead_of_merge(s, seen: dict):
    """Before ``merge-pr``: squash the PR head onto origin's main and mark the stub's PR merged (the stub then refuses its own merge)."""
    def hook() -> None:
        head = s.git("rev-parse", "HEAD")
        base = s.git("--git-dir", s.origin.as_posix(), "rev-parse", "main")
        s.git("fetch", "-q", s.origin.as_posix(), "main")  # origin fetches from a fake URL; the bare remote is its push URL
        squash = s.git("commit-tree", f"{head}^{{tree}}", "-p", base, "-m", f"Release {TAG} (#1)")
        s.git("push", "-q", "origin", f"{squash}:refs/heads/main")
        state_path = s.stub_state / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for pr in state["prs"]:
            pr["state"] = "merged"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        seen.update(H=head, S=squash, base=base, tree=s.git("rev-parse", f"{head}^{{tree}}"))
    return hook


def _publish(s, seen: dict, published: str) -> None:
    """What U3's push-tag will do after its proof: record the merge commit and retag it locally (never a tag already on origin)."""
    record = release_commit.read_state(s.repo)
    record.update(published_commit=published, merged_via="squash", proof={"pr_head": seen["H"], "tree": seen["tree"], "base_before": seen["base"]})
    release_commit.write_state(s.repo, record)
    s.git("tag", "-f", "-a", "-m", f"Release {TAG} (squash of {record['commit'][:10]})", TAG, published)


def _close(driver, s) -> tuple[int, dict]:
    return driver._release(s, "close-phase", "--version", VERSION, "--release-status", "skipped", "--release-note", "no page in this test")


def _squashed_release(make_project) -> tuple:
    s = ss.ready_release(make_project, autonomy="autonomous")
    driver, seen = CliDriver(), {}
    results = release_flow(driver, s, "autonomous", before={"merge-pr": _squash_instead_of_merge(s, seen)})
    assert results[-1].step == "merge-pr" and results[-1].exit_code != 0, [(r.step, r.exit_code) for r in results]  # merged already
    return s, driver, seen


def test_a_squash_merged_release_with_a_valid_proof_passes_the_guard_and_closes_8_of_8(make_project, monkeypatch):
    s, driver, seen = _squashed_release(make_project)
    for key, value in s.env.items():  # the hook runs in this process: give it the scratch's git environment
        monkeypatch.setenv(key, value)
    record = release_commit.read_state(s.repo)
    assert record["commit"] != seen["S"] and s.git("rev-parse", f"{TAG}^{{commit}}") == record["commit"]
    _publish(s, seen, seen["S"])
    assert rg.decide(PUSH, s.repo) is None  # the tag now names S, and the proof holds
    s.git("push", "-q", "origin", f"refs/tags/{TAG}")
    code, out = _close(driver, s)
    assert code == 0 and out["status"] == "ok", out.get("verify")
    assert len(out["verify"]) == 8 and all(c["ok"] for c in out["verify"]), out["verify"]
    assert "\nTag pushed to origin\n" in out["summary"]


@pytest.mark.covers("FR-01.09/AC11")
def test_the_second_close_phase_of_a_guided_release_says_pushed_once_the_tag_is_on_origin(make_project):
    s = ss.ready_release(make_project)
    driver = CliDriver()
    results = release_flow(driver, s, "guided")  # waits for the merge: no tag push, no release page
    assert all(r.exit_code == 0 for r in results), [(r.step, r.exit_code) for r in results]
    code, out = driver._release(s, "close-phase", "--version", VERSION, "--release-status", "waiting", "--release-note", "waits for the PR merge")
    assert code == 0 and "\nTag is pushed after the PR is merged\n" in out["summary"], out.get("verify")
    s.git("push", "-q", "origin", f"refs/tags/{TAG}")  # after the merge the tag goes out
    code, out = _close(driver, s)
    assert code == 0 and "\nTag pushed to origin\n" in out["summary"], out.get("verify")


def test_a_squash_merged_release_whose_tree_does_not_match_is_denied_by_both(make_project, monkeypatch):
    s, driver, seen = _squashed_release(make_project)
    for key, value in s.env.items():
        monkeypatch.setenv(key, value)
    (s.repo / "foreign.txt").write_text("landed next to the release\n", encoding="utf-8")
    s.git("add", "foreign.txt")
    s.git("commit", "-q", "-m", "feat: a foreign change")
    other = s.git("commit-tree", "HEAD^{tree}", "-p", seen["base"], "-m", f"Release {TAG} with a foreign change (#1)")
    s.git("reset", "-q", "--hard", "HEAD~1")
    s.git("push", "-q", "-f", "origin", f"{other}:refs/heads/main")
    _publish(s, seen, other)
    reason = rg.decide(PUSH, s.repo)
    assert reason and "nor its merge commit" in reason
    s.git("push", "-q", "origin", f"refs/tags/{TAG}")  # pushed past the guard by hand: the close must still refuse it
    code, out = _close(driver, s)
    failed = [c["name"] for c in out["verify"] if not c["ok"]]
    assert code == 1 and {"tag_local", "tag_remote", "pr_state"} <= set(failed), out["verify"]
