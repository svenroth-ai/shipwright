"""Tests for shared/scripts/checks/check_worktree_location.py.

Exit-code contract: 0 — isolated worktree (allow), 1 — not (block).
Invocation: subprocess (matches how campaign-mode step 3c and
sub-iterate-runner Step 1.0 call it).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SETUP = (
    _REPO_ROOT / "shared" / "scripts" / "tools" / "setup_iterate_worktree.py"
)
_CHECK = (
    _REPO_ROOT / "shared" / "scripts" / "checks" / "check_worktree_location.py"
)


def _setup(work, slug, run_id):
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_ITERATE_NO_FETCH", None)
    env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
    result = subprocess.run(
        [
            sys.executable, str(_SETUP),
            "--project-root", str(work),
            "--slug", slug, "--run-id", run_id,
        ],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _check(project_root):
    return subprocess.run(
        [sys.executable, str(_CHECK), "--project-root", str(project_root), "--json"],
        capture_output=True, text=True,
    )


def test_check_script_exists():
    assert _CHECK.exists(), f"campaign spawn guard missing at {_CHECK}"


def test_allows_isolated_worktree(git_origin_repo):
    work, _ = git_origin_repo
    payload = _setup(work, "campaign-x", "iterate-campaign-x")
    result = _check(payload["project_root"])
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["decision"] == "allow"


def test_blocks_the_main_repo_checkout(git_origin_repo):
    """The exact incident: a sub-iterate-runner handed the bare main tree."""
    work, _ = git_origin_repo
    result = _check(work)
    assert result.returncode == 1
    assert json.loads(result.stdout)["decision"] == "block"


def test_blocks_a_stray_non_git_directory(tmp_path):
    """Not a Git repo at all — the CLI's documented contract (exit 1, valid
    JSON, no traceback) must hold, not just for the main-repo-checkout case
    (external review, iterate-2026-08-26-campaign-worktree-guard)."""
    stray = tmp_path / "not-a-repo"
    stray.mkdir()
    result = _check(stray)
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"


def test_does_not_require_a_run_id_snapshot(git_origin_repo):
    """A campaign sub-iterate never calls setup_iterate_worktree.py for its own
    run_id, so this guard — unlike check_iterate_isolation.py — must pass on
    an isolated worktree with no Step-1 snapshot at all."""
    work, _ = git_origin_repo
    wt = work / ".worktrees" / "no-snapshot"
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt),
         "-b", "iterate/no-snapshot", "main"],
        capture_output=True, text=True, check=True,
    )
    result = _check(wt)
    assert result.returncode == 0, result.stdout
