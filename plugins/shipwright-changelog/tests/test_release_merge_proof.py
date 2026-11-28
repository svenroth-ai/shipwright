"""U2 (D110 part 1, D113(1)): the release guard and the closing verify accept a proven merge commit, on real git with a bare remote.

After a squash merge the release commit R never reaches the base; the PR's merge commit S does. A record carrying
``published_commit = S`` with a proof whose tree is still S's and the PR head's lets the tag on S through the guard and the
verify. A tree that does not match is denied by both. A record without the new fields behaves as before (no extra git call).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib import release_close, release_commit, release_runstate, release_verify
from lib.release_runner import CmdResult, Recorder, subprocess_runner

from .test_release_guard import VERSION, git, repo as _repo, start_release

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "hooks"))
import release_guard as rg  # noqa: E402
import release_merge_proof as proof  # noqa: E402

repo = _repo  # the fixture, re-exported so pytest finds it in this module
pytestmark = pytest.mark.covers("FR-01.09/AC01")
TAG = f"v{VERSION}"
PUSH = f"git push origin refs/tags/{TAG}"


def _commit(work: Path, name: str, text: str, message: str) -> str:
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(work, "add", name)
    git(work, "commit", "-q", "-m", message)
    return git(work, "rev-parse", "HEAD")


def _squash(work: Path, tree_of: str, parent: str, message: str = "Release (#1)") -> str:
    return git(work, "commit-tree", f"{tree_of}^{{tree}}", "-p", parent, "-m", message)


@pytest.fixture
def merged(repo):
    """R on a release branch, the event commit H on top, and S: a squash of H on origin's main (base moved by nothing)."""
    base = git(repo, "rev-parse", "main")
    git(repo, "checkout", "-q", "-b", "release/next")
    release = _commit(repo, "CHANGELOG.md", "# Changelog\n\n## [1.2.3]\n", "chore(release): v1.2.3")
    head = _commit(repo, ".shipwright/events/drops/e.jsonl", "{}\n", "chore(changelog): record the release event")
    squash = _squash(repo, head, base)
    git(repo, "push", "-q", "origin", f"{squash}:refs/heads/main")
    git(repo, "tag", "-a", "-m", f"Release {TAG} (merge of {release[:10]})", TAG, squash)
    return {"repo": repo, "R": release, "H": head, "S": squash, "base": base, "tree": git(repo, "rev-parse", f"{head}^{{tree}}")}


def _record(m: dict, **over) -> dict:
    body = {"schema": 1, "version": VERSION, "tag": TAG, "commit": m["R"], "checks_passed": ["commit"],
            "published_commit": m["S"], "merged_via": "squash", "proof": {"pr_head": m["H"], "tree": m["tree"], "base_before": m["base"]}}
    body.update(over)
    release_commit.write_state(m["repo"], body)
    return body


def _git_fn(work: Path, calls: list | None = None):
    def run(*args: str) -> tuple[int, str]:
        if calls is not None:
            calls.append(args)
        done = subprocess.run(["git", "-C", str(work), *args], capture_output=True, text=True, encoding="utf-8")
        return done.returncode, done.stdout
    return run


def _foreign(m: dict) -> str:
    """A squash commit whose tree also carries a foreign change (what D112 is about)."""
    repo = m["repo"]
    git(repo, "checkout", "-q", "-b", "foreign", m["H"])
    mixed = _commit(repo, "foreign.txt", "x\n", "feat: landed next to the release")
    git(repo, "checkout", "-q", "release/next")
    return _squash(repo, mixed, m["base"], "Release with a foreign change (#1)")


# ---- the rule ---------------------------------------------------------------------------------------------------------

def test_a_record_without_the_new_fields_claims_nothing_and_costs_no_git_call(merged):
    calls: list = []
    plain = {"commit": merged["R"]}
    assert proof.claimed(plain) is None and proof.proven(_git_fn(merged["repo"], calls), plain) is None and calls == []
    assert proof.accepts(_git_fn(merged["repo"]), plain, merged["R"]) and not proof.accepts(_git_fn(merged["repo"]), plain, merged["S"])


@pytest.mark.parametrize("broken", [{"merged_via": "fast-forward"}, {"proof": None}, {"proof": {"tree": "x"}}, {"published_commit": "abc"},
                                    {"commit": "not-a-sha"}])
def test_a_malformed_claim_is_no_claim(merged, broken):
    record = {"commit": merged["R"], "published_commit": merged["S"], "merged_via": "squash",
              "proof": {"pr_head": merged["H"], "tree": merged["tree"], "base_before": merged["base"]}, **broken}
    assert proof.claimed(record) is None and not proof.accepts(_git_fn(merged["repo"]), record, merged["S"])


def test_a_valid_proof_accepts_the_merge_commit_and_nothing_else(merged):
    record = _record(merged)
    run = _git_fn(merged["repo"])
    assert proof.proven(run, record) == merged["S"] and proof.accepts(run, record, merged["S"])
    assert proof.accepts(run, record, merged["R"]) and proof.accepts(run, record, merged["H"])  # the descent rule still holds
    assert not proof.accepts(run, record, merged["base"]) and not proof.accepts(run, record, "")


def test_a_hand_edited_record_cannot_approve_another_commit(merged):
    other = _foreign(merged)
    run = _git_fn(merged["repo"])
    assert proof.proven(run, _record(merged, published_commit=other)) is None  # its tree is not the release's
    edited = _record(merged, published_commit=other, proof={"pr_head": merged["H"], "tree": git(merged["repo"], "rev-parse", f"{other}^{{tree}}"),
                                                           "base_before": merged["base"]})
    assert proof.proven(run, edited) is None  # the tree matches the commit, but not the release's head
    side = _commit(merged["repo"], "side.txt", "s\n", "feat: not the release")  # a head that is no event-only descendant of R
    assert proof.proven(run, _record(merged, proof={"pr_head": side, "tree": merged["tree"], "base_before": merged["base"]})) is None
    assert proof.proven(run, _record(merged, published_commit="f" * 40)) is None  # a commit this repository does not have


def test_a_commit_with_the_right_tree_but_not_grown_from_the_base_is_not_proven(merged):
    orphan = git(merged["repo"], "commit-tree", f"{merged['H']}^{{tree}}", "-m", "an orphan with the release's tree")
    assert proof.proven(_git_fn(merged["repo"]), _record(merged, published_commit=orphan)) is None


def test_a_rebase_merge_of_the_release_branch_is_proven(merged):
    repo = merged["repo"]
    first = _squash(repo, merged["R"], merged["base"], "chore(release): v1.2.3 (rebased)")  # a rebase merge replays both commits
    tip = _squash(repo, merged["H"], first, "chore(changelog): record the release event (rebased)")
    assert tip != merged["H"]
    record = _record(merged, published_commit=tip, merged_via="rebase")
    assert proof.proven(_git_fn(repo), record) == tip and proof.accepts(_git_fn(repo), record, tip)


def test_a_merge_commit_made_after_the_base_moved_is_not_proven(merged):
    repo = merged["repo"]
    git(repo, "checkout", "-q", "-b", "moved", merged["base"])
    moved = _commit(repo, "other.txt", "o\n", "feat: another PR merged first")
    git(repo, "merge", "-q", "--no-ff", "-m", "Merge the release", merged["H"])
    merge = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "release/next")
    record = _record(merged, published_commit=merge, merged_via="merge", proof={"pr_head": merged["H"], "tree": merged["tree"], "base_before": moved})
    assert proof.claimed(record) == merge and proof.proven(_git_fn(repo), record) is None  # its tree carries the other PR


# ---- the guard -------------------------------------------------------------------------------------------------------

def test_the_guard_allows_the_tag_push_of_a_proven_merge_commit(merged):
    start_release(merged["repo"])
    _record(merged)
    assert rg.decide(PUSH, merged["repo"]) is None
    assert rg.decide("gh release create v1.2.3", merged["repo"]) is None


def test_the_guard_denies_a_merge_commit_whose_tree_does_not_match(merged):
    start_release(merged["repo"])
    other = _foreign(merged)
    git(merged["repo"], "tag", "-f", "-a", "-m", "moved", TAG, other)
    _record(merged, published_commit=other)
    reason = rg.decide(PUSH, merged["repo"])
    assert reason and "nor its merge commit" in reason and other[:10] in reason


def test_the_guard_judges_a_record_without_the_new_fields_as_before(merged):
    start_release(merged["repo"])
    release_commit.write_state(merged["repo"], {"schema": 1, "version": VERSION, "tag": TAG, "commit": merged["R"], "checks_passed": ["commit"]})
    reason = rg.decide(PUSH, merged["repo"])  # the tag names S, the record only R: today's deny, today's advice
    assert reason and "nor its merge commit" not in reason and "neither that commit nor an event-only descendant of it;" in reason


# ---- the closing verify ----------------------------------------------------------------------------------------------

def _runner(key, argv, cwd, **opts):
    """Real git for every git question; the CHANGELOG/tag tool (a uv script) is not what U2 changes."""
    if argv[0] == "git":
        return subprocess_runner(key, argv, cwd, **opts)
    return CmdResult(key, tuple(argv), 0, json.dumps({"ok": True, "checks": {}}), "")


def _verify(m: dict) -> tuple[dict, list[str]]:
    state = {"mode": "standalone", "autonomy": "autonomous", "on_trunk": False, "pr_url": "https://h/o/r/pull/1", "base_branch": "main"}
    rec = Recorder(_runner, m["repo"])
    checks = release_verify.verify(rec, Path(__file__).resolve().parents[1], version=VERSION, state=state, release_status="skipped", release_note="no page here")
    return {c["name"]: c for c in checks}, [r.key for r in rec.results]


def test_the_verify_accepts_the_tag_on_a_proven_merge_commit_and_that_commit_on_the_base(merged):
    _record(merged)
    git(merged["repo"], "push", "-q", "origin", f"refs/tags/{TAG}")
    checks, keys = _verify(merged)
    assert all(checks[n]["ok"] for n in ("tag_local", "tag_remote", "pr_state")), checks
    assert "merge commit" in checks["pr_state"]["detail"] and "verify-proof" in keys


def test_the_verify_denies_a_merge_commit_whose_tree_does_not_match(merged):
    other = _foreign(merged)
    git(merged["repo"], "push", "-q", "-f", "origin", f"{other}:refs/heads/main")
    git(merged["repo"], "tag", "-f", "-a", "-m", "moved", TAG, other)
    git(merged["repo"], "push", "-q", "origin", f"refs/tags/{TAG}")
    _record(merged, published_commit=other)
    checks, _ = _verify(merged)
    assert [n for n in ("tag_local", "tag_remote", "pr_state") if checks[n]["ok"]] == []


def test_the_pr_check_follows_the_tag_a_merge_commit_off_the_base_fails_even_when_the_release_commit_is_on_it(merged):
    git(merged["repo"], "push", "-q", "-f", "origin", f"{merged['H']}:refs/heads/main")  # R reached the base; S (the tag) did not
    _record(merged)
    checks, _ = _verify(merged)
    assert checks["tag_local"]["ok"] and not checks["pr_state"]["ok"] and merged["S"][:10] in checks["pr_state"]["detail"]


def test_the_verify_of_a_record_without_the_new_fields_asks_nothing_new(merged):
    release_commit.write_state(merged["repo"], {"schema": 1, "version": VERSION, "tag": TAG, "commit": merged["R"], "checks_passed": []})
    checks, keys = _verify(merged)
    assert "verify-proof" not in keys and not checks["tag_local"]["ok"] and not checks["pr_state"]["ok"]  # S is not R: today's answer


# ---- D113(1): the closing summary reads what origin holds ------------------------------------------------------------

def _summary(state: dict, remote: dict) -> str:
    return release_close.summary(VERSION, state, [{"name": "tag_remote", "detail": "", **remote}], "skipped", None, "n")


@pytest.mark.covers("FR-01.09/AC11")
@pytest.mark.parametrize(("remote", "line"), [
    ({"ok": True, "on_origin": True}, "Tag pushed to origin"),
    ({"ok": True, "on_origin": False}, "Tag is pushed after the PR is merged"),
    ({"ok": False, "on_origin": True}, f"Tag {TAG} on origin names another commit than the release"),
    ({"ok": False, "on_origin": None}, f"Tag {TAG}: origin could not be asked whether it holds the tag")])
def test_the_summary_of_a_guided_release_says_pushed_only_when_origin_holds_the_tag(remote, line):
    text = _summary({"mode": "standalone", "autonomy": "guided", "on_trunk": False, "pr_url": "u"}, remote)
    assert f"\n\n{line}\n" in text


@pytest.mark.covers("FR-01.09/AC11")
def test_a_release_that_does_not_wait_and_whose_tag_is_missing_says_so():
    text = _summary({"mode": "pipeline", "on_trunk": False, "pr_url": "u"}, {"ok": False, "on_origin": False})
    assert f"Tag {TAG} is not on origin" in text and "Tag pushed to origin" not in text


@pytest.mark.covers("FR-01.09/AC11")
def test_the_second_close_phase_of_a_guided_release_says_pushed_once_the_tag_is_on_origin(merged, plugin_root):
    repo = merged["repo"]
    release_runstate.patch(repo, VERSION, mode="standalone", autonomy="guided", on_trunk=False, pr_url="u", branch="release/next")
    _record(merged)
    git(repo, "tag", "-f", "-a", "-m", "on R", TAG, merged["R"])
    state = release_runstate.stored(repo, VERSION)

    def checks() -> list:
        return release_verify.verify(Recorder(_runner, repo), plugin_root, version=VERSION, state=state, release_status="waiting", release_note="n")

    assert "Tag is pushed after the PR is merged" in release_close.summary(VERSION, state, checks(), "waiting", None, "n")
    git(repo, "push", "-q", "origin", f"refs/tags/{TAG}")  # after the merge the tag goes out
    assert "\nTag pushed to origin\n" in release_close.summary(VERSION, state, checks(), "waiting", None, "n")
