"""Tests for shared/scripts/tools/setup_iterate_worktree.py.

Invocation: subprocess (matches how the iterate skill's Worktree Isolation
step calls it). Exit-code contract:
- 0 — worktree created OR no-op (already inside a worktree)
- 2 — slug collision
- 3 — git fetch failed, no offline override
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT / "shared" / "scripts" / "tools" / "setup_iterate_worktree.py"
)


def _run_setup(project_root, slug, run_id, *, extra_env=None):
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_ITERATE_NO_FETCH", None)
    env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [
            sys.executable, str(_SCRIPT),
            "--project-root", str(project_root),
            "--slug", slug,
            "--run-id", run_id,
        ],
        env=env, capture_output=True, text=True,
    )


def _break_origin(work: Path) -> None:
    subprocess.run(
        [
            "git", "-C", str(work), "remote", "set-url", "origin",
            str(work.parent / "does-not-exist.git"),
        ],
        capture_output=True, text=True, check=True,
    )


def test_script_exists():
    assert _SCRIPT.exists(), f"setup script missing at {_SCRIPT}"


def test_creates_worktree_and_branch(git_origin_repo):
    work, _ = git_origin_repo
    result = _run_setup(work, "my-change", "iterate-20260515-my-change")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "created"
    assert payload["in_worktree"] is False
    wt = Path(payload["project_root"])
    assert wt == (work / ".worktrees" / "my-change")
    assert wt.is_dir()
    assert payload["branch"] == "iterate/my-change"
    branches = subprocess.run(
        ["git", "-C", str(work), "branch", "--list", "iterate/my-change"],
        capture_output=True, text=True,
    ).stdout
    assert "iterate/my-change" in branches


def test_branch_base_is_fresh_origin_default(git_origin_repo):
    work, _ = git_origin_repo
    result = _run_setup(work, "c2", "iterate-c2")
    payload = json.loads(result.stdout)
    assert payload["base_ref"] == "origin/main"
    origin_main = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "origin/main"],
        capture_output=True, text=True,
    ).stdout.strip()
    assert payload["base_commit"] == origin_main


def test_noop_inside_worktree(git_origin_repo):
    work, _ = git_origin_repo
    first = _run_setup(work, "c1", "iterate-c1")
    wt = Path(json.loads(first.stdout)["project_root"])
    # Invoking from inside the worktree must be a pure no-op.
    result = _run_setup(wt, "c1-again", "iterate-c1-again")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "noop"
    assert payload["in_worktree"] is True
    assert Path(payload["project_root"]) == wt
    assert not (work / ".worktrees" / "c1-again").exists()


def test_collision_branch_exists(git_origin_repo):
    work, _ = git_origin_repo
    subprocess.run(
        ["git", "-C", str(work), "branch", "iterate/dup", "main"],
        capture_output=True, text=True, check=True,
    )
    result = _run_setup(work, "dup", "iterate-dup")
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["action"] == "collision"
    assert payload["reason"] == "branch_exists"


def test_collision_worktree_exists(git_origin_repo):
    work, _ = git_origin_repo
    _run_setup(work, "dup2", "iterate-dup2")
    result = _run_setup(work, "dup2", "iterate-dup2b")
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["action"] == "collision"
    assert payload["reason"] in ("worktree_exists", "branch_exists")


def test_fetch_failure_hard_fails(git_origin_repo):
    work, _ = git_origin_repo
    _break_origin(work)
    result = _run_setup(work, "ff", "iterate-ff")
    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["reason"] == "fetch_failed"
    assert not (work / ".worktrees" / "ff").exists()


def test_fetch_failure_override_continues(git_origin_repo):
    work, _ = git_origin_repo
    _break_origin(work)
    result = _run_setup(
        work, "ovr", "iterate-ovr",
        extra_env={"SHIPWRIGHT_ITERATE_NO_FETCH": "1"},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "created"
    assert (work / ".worktrees" / "ovr").is_dir()


def test_noop_inside_worktree_ensures_pointer_and_snapshot(git_origin_repo):
    """Invoked from inside a worktree, setup is a no-op for the worktree but
    still writes the run pointer + a snapshot (if missing) so the F0/F11
    leak-guard has a baseline — closing the review's M1 dead-end."""
    work, _ = git_origin_repo
    first = json.loads(_run_setup(work, "nw", "iterate-nw").stdout)
    wt = first["project_root"]
    result = _run_setup(
        wt, "nw2", "iterate-nw2",
        extra_env={"SHIPWRIGHT_SESSION_ID": "sess-noop"},
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "noop"
    assert Path(payload["pointer_path"]).is_file()
    assert Path(payload["snapshot_path"]).is_file()
    assert payload["snapshot_written"] is True


def test_writes_snapshot_and_pointer(git_origin_repo):
    work, _ = git_origin_repo
    result = _run_setup(
        work, "snp", "iterate-snp",
        extra_env={"SHIPWRIGHT_SESSION_ID": "sess-xyz"},
    )
    payload = json.loads(result.stdout)
    snap = Path(payload["snapshot_path"])
    ptr = Path(payload["pointer_path"])
    assert snap.is_file()
    assert ptr.is_file()
    ptr_data = json.loads(ptr.read_text(encoding="utf-8"))
    assert ptr_data["run_id"] == "iterate-snp"
    assert ptr_data["session_id"] == "sess-xyz"
    assert ptr_data["branch"] == "iterate/snp"
