"""CLI tests for shared/scripts/tools/setup_unit_worktree.py (R2 capability).

Invocation: subprocess, mirroring test_setup_iterate_worktree.py — this
wrapper's own job (identity validation + path-length gate) is what these
tests exercise; the delegated fresh-fetch/gitignore/cleanup behavior itself
is already covered by that file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "shared" / "scripts" / "tools" / "setup_unit_worktree.py"


def _run(project_root, *, campaign_slug="dag-scheduler", unit_id="R2", attempt=None,
         run_id="iterate-20260922-r2-test", max_path=None, extra_env=None):
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_ITERATE_NO_FETCH", None)
    env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
    if extra_env:
        env.update(extra_env)
    args = [
        sys.executable, str(_SCRIPT),
        "--project-root", str(project_root),
        "--campaign-slug", campaign_slug,
        "--unit-id", unit_id,
        "--run-id", run_id,
    ]
    if attempt is not None:
        args += ["--attempt", str(attempt)]
    if max_path is not None:
        args += ["--max-path", str(max_path)]
    return subprocess.run(args, env=env, capture_output=True, text=True)


def test_script_exists():
    assert _SCRIPT.exists(), f"wrapper script missing at {_SCRIPT}"


def test_creates_the_composite_per_unit_worktree(git_origin_repo):
    work, _ = git_origin_repo
    result = _run(work)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "created"
    wt = Path(payload["project_root"])
    assert wt == (work / ".worktrees" / "campaign-dag-scheduler--R2")
    assert wt.is_dir()
    assert payload["branch"] == "iterate/campaign-dag-scheduler--R2"


def test_attempt_suffix_changes_the_worktree_name(git_origin_repo):
    work, _ = git_origin_repo
    result = _run(work, attempt=1)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    wt = Path(payload["project_root"])
    assert wt == (work / ".worktrees" / "campaign-dag-scheduler--R2-a1")


def test_invalid_campaign_slug_is_rejected_before_touching_git(git_origin_repo):
    work, _ = git_origin_repo
    result = _run(work, campaign_slug="bad slug!")
    assert result.returncode == 4, result.stdout
    payload = json.loads(result.stdout)
    assert payload["reason"] == "invalid_identity"
    assert not (work / ".worktrees").exists()


def test_invalid_unit_id_is_rejected_before_touching_git(git_origin_repo):
    work, _ = git_origin_repo
    result = _run(work, unit_id="../etc")
    assert result.returncode == 4, result.stdout


def test_repeat_call_for_the_same_unit_is_a_clean_collision_not_partial_state(git_origin_repo):
    """A second call for the SAME (campaign_slug, unit_id) must refuse
    cleanly (exit 2, delegated unchanged from setup_iterate_worktree.py's
    own slug-collision handling) rather than partially recreate or corrupt
    the first worktree (external plan review, OpenAI, medium)."""
    work, _ = git_origin_repo
    first = _run(work)
    assert first.returncode == 0, first.stderr

    second = _run(work, run_id="iterate-20260922-r2-test-2")
    assert second.returncode == 2, second.stdout
    payload = json.loads(second.stdout)
    assert payload["action"] == "collision"

    # The original worktree is untouched by the failed second attempt.
    wt = work / ".worktrees" / "campaign-dag-scheduler--R2"
    assert wt.is_dir()


def test_path_too_long_is_rejected_before_touching_git(git_origin_repo):
    """The wrapper's own path-length gate must fire and exit 5 BEFORE any
    git call. Uses ``--max-path`` (added for exactly this: a deterministic
    tight bound, independent of this machine's own tmp-dir depth) rather
    than depending on a real 260+-character filesystem path existing on
    every dev machine / CI runner — the real Windows MAX_PATH default is
    exercised by ``lib.campaign_unit_worktree``'s own unit tests
    (test_campaign_unit_worktree.py)."""
    work, _ = git_origin_repo
    long_slug = "s" * 40
    long_unit = "u" * 64
    result = _run(work, campaign_slug=long_slug, unit_id=long_unit, max_path=10)
    assert result.returncode == 5, result.stdout
    payload = json.loads(result.stdout)
    assert payload["reason"] == "path_too_long"
    assert long_slug in payload["detail"]
    assert long_unit in payload["detail"]
    assert not (work / ".worktrees").exists()
