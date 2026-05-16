"""Tests for shared/scripts/checks/check_iterate_isolation.py (leak-guard).

Exit-code contract: 0 — isolated (allow), 1 — isolation violated (block).
Invocation: subprocess (matches how skill F0 / F11 call it).
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
    _REPO_ROOT / "shared" / "scripts" / "checks" / "check_iterate_isolation.py"
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


def _check(project_root, run_id):
    return subprocess.run(
        [
            sys.executable, str(_CHECK),
            "--project-root", str(project_root),
            "--run-id", run_id, "--json",
        ],
        capture_output=True, text=True,
    )


def test_check_script_exists():
    assert _CHECK.exists(), f"leak-guard missing at {_CHECK}"


def test_allows_clean_isolated_worktree(git_origin_repo):
    work, _ = git_origin_repo
    payload = _setup(work, "clean", "iterate-clean")
    result = _check(payload["project_root"], "iterate-clean")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["decision"] == "allow"


def test_blocks_when_run_in_main_repo(git_origin_repo):
    work, _ = git_origin_repo
    _setup(work, "m", "iterate-m")
    # Guard pointed at the MAIN repo, not the worktree → must block.
    result = _check(work, "iterate-m")
    assert result.returncode == 1
    assert json.loads(result.stdout)["reason"] == "not_under_worktrees"


def test_blocks_on_main_tree_leak(git_origin_repo):
    work, _ = git_origin_repo
    payload = _setup(work, "leak", "iterate-leak")
    # A NEW dirty file appears in the main tree after Step 1 → leak.
    (work / "leaked_by_run.txt").write_text("oops", encoding="utf-8")
    result = _check(payload["project_root"], "iterate-leak")
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["reason"] == "main_tree_leak"
    assert "leaked_by_run.txt" in data["new_paths"]


def test_tolerates_preexisting_main_tree_dirt(git_origin_repo):
    work, _ = git_origin_repo
    # Dirt present BEFORE setup → captured in the Step-1 snapshot.
    (work / "preexisting.txt").write_text("noise", encoding="utf-8")
    payload = _setup(work, "pre", "iterate-pre")
    result = _check(payload["project_root"], "iterate-pre")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["decision"] == "allow"


def test_blocks_when_snapshot_missing(git_origin_repo):
    work, _ = git_origin_repo
    payload = _setup(work, "nosnap", "iterate-nosnap")
    Path(payload["snapshot_path"]).unlink()  # simulate a run that skipped Step 1
    result = _check(payload["project_root"], "iterate-nosnap")
    assert result.returncode == 1
    assert json.loads(result.stdout)["reason"] == "no_snapshot"
