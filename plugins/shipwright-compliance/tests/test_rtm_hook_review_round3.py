"""check_rtm_coverage follow-ups from U13 code review round 3 (commit scope, heredocs, work tree)."""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import compliance_override as co  # noqa: E402
import git_commit_command as gcc  # noqa: E402
import git_commit_target as gct  # noqa: E402
import rtm_commit_scope as rcs  # noqa: E402

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import (  # noqa: E402
    collector_manifest, commit_all, hook_env, init_repo, write_manifest)
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
HOOK = Path(__file__).parent.parent / "scripts" / "hooks" / "check_rtm_coverage.py"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(cwd: Path, command: str, tmp_root: Path):
    payload = {"tool_input": {"command": command}, "cwd": str(cwd)}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(cwd),
                          env=hook_env(tmp_root), timeout=60)


# --- 1: a multi-repo line carries the WARNs of the repos it is not judged on -------------

def test_an_unmeasurable_second_repo_is_never_dropped_silently(tmp_path, monkeypatch):
    low, blind = tmp_path / "low", tmp_path / "blind"
    low.mkdir()
    blind.mkdir()

    def measure(root):
        if Path(root).name == "blind":
            return None, ["no manifest here", rcs.gate.NOT_EVALUATING]
        return {"pct": 30}, ["low's own note"]

    monkeypatch.setattr(rcs.gate, "measure", measure)
    monkeypatch.setattr(rcs.gate, "meets", lambda *_a: False)
    monkeypatch.setattr(rcs.gate, "read_threshold", lambda _root: (80.0, [], None))
    scope = rcs.commit_scope(f'git -C "{low}" commit -m a && git -C "{blind}" commit -m b',
                             str(tmp_path), lambda: str(tmp_path))
    assert Path(scope.root).name == "low"
    blind_root = next(r for r in scope.warnings if "no manifest here" in r)
    assert blind_root.startswith("[") and "blind" in blind_root
    assert any(w.startswith("[") and rcs.gate.NOT_EVALUATING in w for w in scope.warnings)
    assert not any("low's own note" in w for w in scope.warnings)  # travels in .measured
    assert scope.measured == ({"pct": 30}, ["low's own note"])


# --- 4: one repo spelled two ways is one repo ---------------------------------------------

def test_repo_key_folds_resolution_and_case(tmp_path):
    (tmp_path / "Repo").mkdir()
    assert rcs.repo_key(tmp_path / "Repo" / ".." / "Repo") == rcs.repo_key(tmp_path / "Repo")
    if os.name == "nt":
        assert rcs.repo_key(str(tmp_path / "REPO")) == rcs.repo_key(tmp_path / "Repo")


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive paths are a Windows property")
def test_case_variants_of_one_repo_are_not_a_multi_repo_line(tmp_path, monkeypatch):
    repo = tmp_path / "Repo"
    repo.mkdir()
    monkeypatch.setattr(rcs.gate, "measure", lambda _root: pytest.fail("measured"))
    upper = str(repo).upper()
    scope = rcs.commit_scope(f'git -C "{upper}" commit && git commit', str(tmp_path),
                             lambda: str(repo))
    assert not any("repos (" in w for w in scope.warnings) and scope.measured is None


# --- 2 / 3 / doubt review: heredocs inside "$(...)", -s, more interpreters ----------------

CANONICAL = ("git commit -m \"$(cat <<'EOF'\nfix: say \"odd quote\nmention <<NEXT here\n"
             "EOF\n)\"\ngit -C ../x commit -m y")


def test_the_canonical_commit_message_heredoc_is_stripped():
    assert list(gcc.iter_git_commits(CANONICAL)) == [(), ("-C", "../x")]
    inner = "git commit -m \"$(cat <<'EOF'\nsay \"odd\nthen; git -C ../o commit\nEOF\n)\""
    assert list(gcc.iter_git_commits(inner)) == [()]  # a commit named in the message is data


@pytest.mark.parametrize("command", [
    "git commit -s -F - <<EOF\ngit -C ../x commit -m inner\nEOF",  # -s is sign-off here
    "git -C . commit -F - <<EOF\ngit -C ../x commit -m inner\nEOF",  # `.` as an argument
])
def test_a_commit_message_body_is_data(command):
    assert len(list(gcc.iter_git_commits(command))) == 1


def test_dash_s_of_a_non_shell_feeds_no_shell():
    assert not gcc.is_git_commit("runner -s <<EOF\ngit commit\nEOF")


@pytest.mark.parametrize("command", [
    "sudo -s <<EOF\ngit commit -m x\nEOF", "bash -s <<EOF\ngit commit -m x\nEOF",
    "source /dev/stdin <<EOF\ngit commit -m x\nEOF", ". /dev/stdin <<EOF\ngit commit\nEOF",
    "fish <<EOF\ngit commit -m x\nEOF", "cat <<EOF | fish\ngit commit -m x\nEOF",
    'echo "a <<EOF"\ngit commit -m x',  # outside $(...) a quoted operator is still inert
])
def test_bodies_fed_to_a_shell_still_fire(command):
    assert gcc.is_git_commit(command)


# --- 5: the override lock file is ignored ---------------------------------------------------

def test_the_override_lock_is_in_both_gitignores():
    lock = co.LOG_RELPATH.with_name(co.LOG_RELPATH.name + ".lock").as_posix()
    for path in (REPO_ROOT / ".gitignore",
                 REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert "/.shipwright/agent_docs/*.log.lock" in lines, path
    assert fnmatch.fnmatch(lock, ".shipwright/agent_docs/*.log.lock")


# --- 7: a --work-tree target is resolved like -C -------------------------------------------

@needs_git
def test_a_monorepo_work_tree_descends_into_the_project(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    init_repo(repo)
    write_manifest(repo / "app", collector_manifest(3, 10, executed_rest="fail"))
    (repo / "app" / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    commit_all(repo)
    target = gct.commit_target("git --work-tree=. commit", repo)
    assert target.project_root == repo / "app" and target.found and target.work_tree == repo
    scope = rcs.commit_scope("git --work-tree=. commit", str(repo), lambda: str(repo))
    assert scope.env["GIT_WORK_TREE"] == str(repo)
    blocked = _run(repo, "git --work-tree=. commit -m x", tmp_path)
    assert blocked.returncode == 2 and "(3/10 active" in blocked.stderr


def test_a_work_tree_with_no_project_is_flagged(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    target = gct.commit_target(f'git --git-dir=x.git --work-tree="{bare}" commit', tmp_path)
    assert not target.found and target.work_tree == bare and target.git_dir is not None
