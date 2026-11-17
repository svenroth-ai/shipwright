"""The ``gh`` stub contract (golden-trace harness): what it refuses, what it really does, what it logs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (programme P2a); the gate refuses removing it (tag-removed), see the P2b1 FINDINGS note
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "testkit"))

import release_scratch as rs  # noqa: E402

_CREATE_RELEASE = _REPO_ROOT / "shared" / "scripts" / "tools" / "create_github_release.py"


@pytest.fixture
def scratch(tmp_path: Path) -> rs.Scratch:
    return rs.build_scratch(tmp_path / "s")


def gh(s: rs.Scratch, *args: str) -> subprocess.CompletedProcess:
    return s.run([*json.loads(s.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"]), *args])


def push_feature(s: rs.Scratch, branch: str = "feat/x", name: str = "a.txt", text: str = "a\n") -> None:
    s.git("checkout", "-q", "-b", branch)
    (s.repo / name).write_text(text, encoding="utf-8")
    s.git("add", "-A")
    s.git("commit", "-q", "-m", f"feat: add {name}")
    s.git("push", "-q", "origin", branch)


def remote_refs(s: rs.Scratch) -> dict[str, str]:
    rows = s.git("ls-remote", s.origin.as_posix()).splitlines()
    return {r.split("\t")[1]: r.split("\t")[0] for r in rows}


def test_pr_create_refuses_a_head_branch_that_is_not_on_the_remote(scratch):
    scratch.git("checkout", "-q", "-b", "feat/local-only")
    done = gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    assert done.returncode == 1 and "not on the remote" in done.stderr
    assert scratch.gh_state()["prs"] == []


def test_pr_create_records_the_pr_once_the_head_is_pushed(scratch):
    push_feature(scratch)
    done = gh(scratch, "pr", "create", "--title", "Release v1", "--body", "## Changelog", "--base", "main")
    assert done.returncode == 0
    assert done.stdout.strip() == f"https://github.com/{rs.FAKE_SLUG}/pull/1"
    assert scratch.gh_state()["prs"] == [{"number": 1, "head": "feat/x", "base": "main", "title": "Release v1",
                                          "body": "## Changelog", "state": "open"}]


def test_pr_create_defaults_the_base_to_the_remote_default_branch(tmp_path):
    s = rs.build_scratch(tmp_path / "m", default_branch="master")
    push_feature(s)
    assert gh(s, "pr", "create", "--title", "t", "--body", "b").returncode == 0
    assert s.gh_state()["prs"][0]["base"] == "master"


@pytest.mark.parametrize(("flags", "code"), [([], 1), (["--squash"], 2), (["--rebase"], 2)])
def test_pr_merge_refuses_without_a_merge_flag_and_for_unsupported_ones(scratch, flags, code):
    push_feature(scratch)
    gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    before = remote_refs(scratch)
    assert gh(scratch, "pr", "merge", *flags).returncode == code
    assert remote_refs(scratch) == before


def test_pr_merge_really_merges_into_the_remote_base_and_deletes_the_head(scratch):
    push_feature(scratch)
    head_sha = scratch.git("rev-parse", "HEAD")
    gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    done = gh(scratch, "pr", "merge", "--merge", "--delete-branch")
    assert done.returncode == 0, done.stderr
    refs = remote_refs(scratch)
    assert "refs/heads/feat/x" not in refs
    check = scratch.run(["git", "--git-dir", scratch.origin.as_posix(), "log", "-1", "--format=%s%n%P", "main"])
    subject, parents = check.stdout.splitlines()
    assert subject == "Merge pull request #1 from feat/x" and head_sha in parents.split()
    assert scratch.gh_state()["prs"][0]["state"] == "merged"


def test_pr_merge_delete_branch_leaves_a_checkout_on_the_head_on_the_merged_base(scratch):
    push_feature(scratch)
    gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    assert gh(scratch, "pr", "merge", "--merge", "--delete-branch").returncode == 0
    assert scratch.git("rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert scratch.git("branch", "--list", "feat/x") == ""  # the local head is deleted
    assert scratch.git("rev-parse", "main") == remote_refs(scratch)["refs/heads/main"]  # fast-forwarded to the merge
    assert scratch.git("log", "-1", "--format=%s") == "Merge pull request #1 from feat/x"


def test_a_release_tag_and_main_push_after_the_merge_succeeds(scratch):
    """SKILL.md Step 7, autonomous path: tag on the head, merge with --delete-branch, then push the tags and main."""
    push_feature(scratch)
    scratch.git("tag", "-a", "v0.2.0", "-m", "Release v0.2.0")
    gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    assert gh(scratch, "pr", "merge", "--merge", "--delete-branch").returncode == 0
    pushed = scratch.run(["git", "push", "--tags", "origin", "main"])
    assert pushed.returncode == 0, pushed.stderr
    assert "refs/tags/v0.2.0" in remote_refs(scratch)


def test_pr_merge_delete_branch_from_another_branch_leaves_the_checkout_alone(scratch):
    push_feature(scratch)
    scratch.git("checkout", "-q", "main")
    gh(scratch, "pr", "create", "--head", "feat/x", "--title", "t", "--body", "b", "--base", "main")
    assert gh(scratch, "pr", "merge", "feat/x", "--merge", "--delete-branch").returncode == 0
    assert scratch.git("rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert scratch.git("branch", "--list", "feat/x") != ""  # only a checkout that sat on the head is switched


def test_pr_merge_without_delete_branch_keeps_the_head(scratch):
    push_feature(scratch)
    gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    assert gh(scratch, "pr", "merge", "--merge").returncode == 0
    assert "refs/heads/feat/x" in remote_refs(scratch)


def test_pr_merge_with_no_open_pr_refuses(scratch):
    push_feature(scratch)
    done = gh(scratch, "pr", "merge", "--merge")
    assert done.returncode == 1 and "no open pull request" in done.stderr


def test_pr_merge_refuses_a_conflict_and_leaves_the_remote_alone(scratch):
    push_feature(scratch, "feat/one", "same.txt", "one\n")
    gh(scratch, "pr", "create", "--title", "1", "--body", "b", "--base", "main")
    scratch.git("checkout", "-q", "main")
    push_feature(scratch, "feat/two", "same.txt", "two\n")
    gh(scratch, "pr", "create", "--title", "2", "--body", "b", "--base", "main")
    assert gh(scratch, "pr", "merge", "feat/one", "--merge").returncode == 0
    before = remote_refs(scratch)
    done = gh(scratch, "pr", "merge", "feat/two", "--merge")
    assert done.returncode == 1 and "not mergeable" in done.stderr
    assert remote_refs(scratch) == before


def test_release_create_refuses_a_tag_that_is_not_on_the_remote(scratch):
    scratch.git("tag", "v0.2.0")  # local only
    done = gh(scratch, "release", "create", "v0.2.0", "--notes", "n", "--verify-tag")
    assert done.returncode == 1 and "not found on the remote" in done.stderr
    assert gh(scratch, "release", "view", "v0.2.0").returncode == 1


def test_release_create_persists_and_a_later_view_returns_it(scratch):
    miss = gh(scratch, "release", "view", "v0.1.0", "--repo", rs.FAKE_SLUG, "--json", "url")
    assert miss.returncode == 1 and "release not found" in miss.stderr
    notes = scratch.repo / "notes.md"
    notes.write_text("## Highlights\n\nhello\n", encoding="utf-8")
    made = gh(scratch, "release", "create", "v0.1.0", "--notes-file", str(notes), "--title", "v0.1.0")
    assert made.returncode == 0
    seen = gh(scratch, "release", "view", "v0.1.0", "--json", "url")
    assert json.loads(seen.stdout) == {"url": f"https://github.com/{rs.FAKE_SLUG}/releases/tag/v0.1.0"}
    assert scratch.gh_state()["releases"]["v0.1.0"]["notes"].startswith("## Highlights")
    assert gh(scratch, "release", "create", "v0.1.0", "--notes", "again").returncode == 1


def test_every_call_lands_in_the_argv_log_in_order_refusals_included(scratch):
    gh(scratch, "--version")
    gh(scratch, "release", "view", "v9.9.9")
    gh(scratch, "frobnicate")
    assert scratch.gh_argv_log() == [{"argv": ["--version"], "exit": 0},
                                     {"argv": ["release", "view", "v9.9.9"], "exit": 1},
                                     {"argv": ["frobnicate"], "exit": 2}]


def test_without_a_state_directory_the_stub_refuses_to_pretend(scratch):
    env = {k: v for k, v in scratch.env.items() if k != "SHIPWRIGHT_GH_STUB_STATE"}
    prefix = json.loads(env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"])
    done = subprocess.run([*prefix, "--version"], env=env, cwd=scratch.repo, capture_output=True, text=True)
    assert done.returncode == 3 and "not set" in done.stderr


def test_a_corrupt_state_file_fails_loudly(scratch):
    (scratch.stub_state / "state.json").write_text("{not json", encoding="utf-8")
    done = gh(scratch, "release", "view", "v0.1.0")
    assert done.returncode == 3 and "corrupt" in done.stderr


def _create_release(s: rs.Scratch, version: str, notes: Path) -> dict:
    done = s.run([sys.executable, str(_CREATE_RELEASE), "--project-root", str(s.repo), "--version", version,
                  "--notes-file", str(notes)])
    return json.loads(done.stdout)


def test_the_real_release_script_publishes_through_the_stub_and_is_refused_for_an_unpushed_tag(scratch):
    notes = scratch.repo / "notes.md"
    notes.write_text("## Highlights\n\nShip it.\n", encoding="utf-8")
    first = _create_release(scratch, "0.1.0", notes)
    assert first["status"] == "ok" and first["seam"] == "gh"
    assert _create_release(scratch, "0.1.0", notes)["status"] == "exists"
    scratch.git("tag", "v0.2.0")  # never pushed
    refused = _create_release(scratch, "0.2.0", notes)
    assert refused["status"] == "failed" and "not found on the remote" in refused["reason"]
    assert "v0.2.0" not in scratch.gh_state()["releases"]
    assert [e["argv"][:2] for e in scratch.gh_argv_log()].count(["release", "create"]) == 2


def test_a_bare_gh_in_the_scratch_environment_is_the_stub_and_a_real_gh_is_logged_out(scratch):
    found = shutil.which("gh", path=scratch.env["PATH"])
    assert found and Path(found).parent == scratch.stub_state / "bin"  # a bare gh resolves to the shim first
    assert shutil.which("git", path=scratch.env["PATH"])  # and git is still reachable
    assert Path(scratch.env["GH_CONFIG_DIR"]).parent == scratch.stub_state and scratch.env["GH_PROMPT_DISABLED"] == "1"
    shim = scratch.run([str(scratch.stub_state / "bin" / ("gh.cmd" if os.name == "nt" else "gh")), "--version"])
    assert shim.returncode == 0 and "gh version" in shim.stdout
    assert scratch.gh_argv_log() == []  # a bare gh stays out of the trace log
    unseamed = (scratch.stub_state / "unseamed.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(unseamed[-1]) == {"argv": ["--version"], "exit": 0}


def test_a_bare_gh_is_not_logged_in_and_a_seamed_one_is(scratch):
    """Windows never lets a bare ``gh`` reach the stub; on Linux it would, and ``auth status`` answering yes made the
    audit probe the code host there only (a different trace per OS). A bare gh is logged out; the seam's is not."""
    shim = str(scratch.stub_state / "bin" / ("gh.cmd" if os.name == "nt" else "gh"))
    assert scratch.run([shim, "auth", "status"]).returncode == 1
    assert scratch.run([shim, "pr", "create", "-t", "t", "-b", "b"]).returncode == 4  # a bare gh never acts
    assert gh(scratch, "auth", "status").returncode == 0
    assert scratch.gh_argv_log() == [{"argv": ["auth", "status"], "exit": 0}]  # only the seamed call is in the trace log
    unseamed = [json.loads(x) for x in (scratch.stub_state / "unseamed.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["exit"] for e in unseamed] == [1, 4]
    assert scratch.gh_state()["prs"] == []


def test_pr_create_refuses_what_real_gh_refuses(scratch):
    push_feature(scratch)
    assert gh(scratch, "pr", "create", "-t", "t", "-b", "b", "-B", "nope").returncode == 1  # base not on the remote
    assert gh(scratch, "pr", "create", "-t", "t", "-b", "b", "-B", "main").returncode == 0  # short flags work
    again = gh(scratch, "pr", "create", "-t", "t", "-b", "b", "-B", "main")
    assert again.returncode == 1 and "already exists" in again.stderr


def test_short_flags_are_per_command(scratch):
    notes = scratch.repo / "n.md"
    notes.write_text("## Highlights\n", encoding="utf-8")
    made = gh(scratch, "release", "create", "v0.1.0", "-t", "Title", "-F", str(notes), "-p", "-d")
    assert made.returncode == 0, made.stderr
    release = scratch.gh_state()["releases"]["v0.1.0"]
    assert release["title"] == "Title" and release["notes"].startswith("## Highlights")
    assert gh(scratch, "release", "create", "v0.1.1", "-b", "x").returncode == 2  # -b is a pr create flag
    assert gh(scratch, "release", "create", "v0.1.1", "-md").returncode == 2  # bundled short flags are refused
    push_feature(scratch)
    assert gh(scratch, "pr", "create", "-t", "t", "-F", str(notes), "-B", "main").returncode == 0
    assert scratch.gh_state()["prs"][0]["body"].startswith("## Highlights")  # -F is the body file on a PR
    assert gh(scratch, "pr", "create", "-n", "x").returncode == 2  # -n is a release flag


def test_an_unsupported_short_flag_or_a_flag_without_a_value_is_refused_not_guessed(scratch):
    push_feature(scratch)
    assert gh(scratch, "pr", "create", "-x").returncode == 2
    missing = gh(scratch, "pr", "create", "--title", "--body", "b")
    assert missing.returncode == 2 and "needs a value" in missing.stderr
    assert gh(scratch, "pr", "merge", "-m", "-d").returncode == 1  # parsed as --merge --delete-branch: no open PR


def test_a_crash_inside_the_stub_still_reaches_the_argv_log(scratch):
    done = gh(scratch, "release", "create", "v0.1.0", "--notes-file", str(scratch.repo / "missing.md"))
    assert done.returncode == 4 and "internal error" in done.stderr
    assert scratch.gh_argv_log()[-1]["exit"] == 4


def test_a_long_flag_the_contract_does_not_list_is_refused_and_does_not_leak_into_the_positionals(scratch):
    push_feature(scratch)
    gh(scratch, "pr", "create", "--title", "t", "--body", "b", "--base", "main")
    done = gh(scratch, "pr", "merge", "--subject", "X", "1", "--merge")
    assert done.returncode == 2 and "unsupported flag --subject" in done.stderr
    assert gh(scratch, "release", "create", "--discussion-category", "C", "v0.1.0").returncode == 2
