"""Integration test: two parallel /shipwright-iterate runs stay isolated.

Drives ``setup_iterate_worktree.py`` + ``check_iterate_isolation.py`` through
two simulated concurrent iterate runs and proves the non-negotiable
invariants from ``.shipwright/planning/iterate/2026-05-15-iterate-worktree-isolation.md``:

- each run gets its OWN worktree + branch, both cut from a fresh
  ``origin/<default>``
- neither run can write into the other's worktree, nor into the main tree
- the main repo working tree stays clean
- a slug collision is rejected cleanly, with no partial state
- a real leak into the main tree is caught by the F0/F11 leak-guard
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP = REPO_ROOT / "shared" / "scripts" / "tools" / "setup_iterate_worktree.py"
CHECK = REPO_ROOT / "shared" / "scripts" / "checks" / "check_iterate_isolation.py"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Iso IT",
    "GIT_AUTHOR_EMAIL": "iso@it.invalid",
    "GIT_COMMITTER_NAME": "Iso IT",
    "GIT_COMMITTER_EMAIL": "iso@it.invalid",
}


def _git(cwd, *args):
    env = os.environ.copy()
    env.update(_GIT_ENV)
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env,
        capture_output=True, text=True, check=True,
    )


@pytest.fixture
def main_repo(tmp_path):
    """Main repo working tree with a local bare origin + tracked ``.shipwright/``."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(work))
    (work / "README.md").write_text("root\n", encoding="utf-8")
    (work / ".shipwright").mkdir()
    (work / ".shipwright" / ".gitkeep").write_text("", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "main")
    _git(work, "remote", "set-head", "origin", "main")
    return work


def _setup(work, slug, run_id, session_id):
    env = os.environ.copy()
    env.update(_GIT_ENV)
    env.pop("SHIPWRIGHT_ITERATE_NO_FETCH", None)
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [
            sys.executable, str(SETUP),
            "--project-root", str(work),
            "--slug", slug, "--run-id", run_id,
        ],
        env=env, capture_output=True, text=True,
    )


def _check(project_root, run_id):
    return subprocess.run(
        [
            sys.executable, str(CHECK),
            "--project-root", str(project_root),
            "--run-id", run_id, "--json",
        ],
        capture_output=True, text=True,
    )


def _main_tree_clean(work) -> bool:
    """True if ``git status`` shows nothing but run scaffolding.

    ``.worktrees/`` and ``.shipwright/runs|iterate_active`` are this run's
    own infrastructure — never a leak. Any OTHER dirty path is.
    """
    out = _git(work, "status", "--porcelain").stdout
    leaked = [
        ln for ln in out.splitlines()
        if ln.strip()
        and not ln[3:].lstrip().startswith((".shipwright/", ".worktrees/"))
    ]
    return not leaked


class TestTwoParallelIterates:
    def test_each_run_gets_own_worktree_and_branch(self, main_repo):
        a = _setup(main_repo, "feat-a", "iterate-20260515-feat-a", "sess-A")
        b = _setup(main_repo, "feat-b", "iterate-20260515-feat-b", "sess-B")
        assert a.returncode == 0, a.stderr
        assert b.returncode == 0, b.stderr
        pa, pb = json.loads(a.stdout), json.loads(b.stdout)
        wt_a, wt_b = Path(pa["project_root"]), Path(pb["project_root"])
        assert wt_a != wt_b
        assert wt_a.is_dir() and wt_b.is_dir()
        assert pa["branch"] == "iterate/feat-a"
        assert pb["branch"] == "iterate/feat-b"
        # Both branched from the SAME fresh origin/main — never local main,
        # never each other.
        origin_main = _git(main_repo, "rev-parse", "origin/main").stdout.strip()
        assert pa["base_commit"] == origin_main
        assert pb["base_commit"] == origin_main

    def test_no_cross_tree_write(self, main_repo):
        a = json.loads(_setup(main_repo, "wa", "iterate-wa", "sess-A").stdout)
        b = json.loads(_setup(main_repo, "wb", "iterate-wb", "sess-B").stdout)
        wt_a, wt_b = Path(a["project_root"]), Path(b["project_root"])
        (wt_a / "only_in_a.txt").write_text("a", encoding="utf-8")
        assert (wt_a / "only_in_a.txt").exists()
        assert not (wt_b / "only_in_a.txt").exists()
        assert not (main_repo / "only_in_a.txt").exists()

    def test_main_tree_stays_clean(self, main_repo):
        _setup(main_repo, "ca", "iterate-ca", "sess-A")
        _setup(main_repo, "cb", "iterate-cb", "sess-B")
        assert _main_tree_clean(main_repo), (
            _git(main_repo, "status", "--porcelain").stdout
        )

    def test_both_runs_pass_the_leak_guard(self, main_repo):
        a = json.loads(_setup(main_repo, "ga", "iterate-ga", "sess-A").stdout)
        b = json.loads(_setup(main_repo, "gb", "iterate-gb", "sess-B").stdout)
        ra = _check(a["project_root"], "iterate-ga")
        rb = _check(b["project_root"], "iterate-gb")
        assert ra.returncode == 0, ra.stdout
        assert rb.returncode == 0, rb.stdout

    def test_slug_collision_rejected(self, main_repo):
        first = _setup(main_repo, "dup", "iterate-dup-1", "sess-A")
        assert first.returncode == 0, first.stderr
        second = _setup(main_repo, "dup", "iterate-dup-2", "sess-B")
        assert second.returncode == 2
        assert json.loads(second.stdout)["action"] == "collision"

    def test_leak_into_main_tree_is_caught(self, main_repo):
        a = json.loads(_setup(main_repo, "la", "iterate-la", "sess-A").stdout)
        # A run leaks a NEW file into the main tree after Step 1.
        (main_repo / "leaked.txt").write_text("oops", encoding="utf-8")
        result = _check(a["project_root"], "iterate-la")
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["reason"] == "main_tree_leak"
        assert "leaked.txt" in data["new_paths"]
