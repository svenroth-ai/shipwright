"""Integration test: the campaign-worktree step-0 flow, end to end.

Composes the REAL producer (`setup_iterate_worktree.py`, which creates the
actual campaign worktree campaign-mode.md's Setup step depends on) with BOTH
guards this iterate adds around it — the session-liveness lock
(`check_campaign_session_lock.py`) and the worktree-identity check
(`check_worktree_location.py --campaign-slug`) — rather than unit-testing
each against a hand-built fixture in isolation. This is the
`category:"integration"` behavior for the `cross_component` flag
(campaign-mode.md is in this diff): it proves the pieces compose on the
artifact the real Setup step actually produces.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _worktree_setup_helper import run_setup_iterate_worktree  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCATION_CHECK = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_worktree_location.py"
_SESSION_LOCK = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_campaign_session_lock.py"


def _lock(project_root, session_id, *, stale_after_seconds=None):
    argv = [sys.executable, str(_SESSION_LOCK), "acquire",
            "--campaign-worktree", str(project_root),
            "--session-id", session_id, "--json"]
    if stale_after_seconds is not None:
        argv += ["--stale-after-seconds", str(stale_after_seconds)]
    return subprocess.run(argv, capture_output=True, text=True)


def _location(project_root, campaign_slug):
    return subprocess.run(
        [sys.executable, str(_LOCATION_CHECK), "--project-root", str(project_root),
         "--campaign-slug", campaign_slug, "--json"],
        capture_output=True, text=True,
    )


def test_real_campaign_worktree_passes_both_guards_for_its_own_session_and_slug(
    git_origin_repo,
):
    work, _ = git_origin_repo
    project_root = run_setup_iterate_worktree(work, "campaign-demo", "iterate-campaign-demo")["project_root"]

    acquired = _lock(project_root, "sess-a")
    assert acquired.returncode == 0, acquired.stdout + acquired.stderr
    assert json.loads(acquired.stdout)["decision"] == "allow"

    allowed = _location(project_root, "demo")
    assert allowed.returncode == 0, allowed.stdout
    assert json.loads(allowed.stdout)["decision"] == "allow"


def test_a_second_live_session_is_rejected_a_dead_one_reclaims(git_origin_repo):
    """The card's own liveness test: second start refused while the first is
    live, admitted once the first is presumed dead."""
    work, _ = git_origin_repo
    project_root = run_setup_iterate_worktree(work, "campaign-demo", "iterate-campaign-demo")["project_root"]
    assert _lock(project_root, "sess-a").returncode == 0

    still_live = _lock(project_root, "sess-b", stale_after_seconds=9999)
    assert still_live.returncode == 1
    assert json.loads(still_live.stdout)["decision"] == "block"

    presumed_dead = _lock(project_root, "sess-b", stale_after_seconds=0)
    assert presumed_dead.returncode == 0, presumed_dead.stdout + presumed_dead.stderr
    assert json.loads(presumed_dead.stdout)["decision"] == "allow"


def test_a_misdirected_project_root_pointing_at_a_foreign_campaign_is_rejected(
    git_origin_repo,
):
    """The card's own identity test: a project_root that IS an isolated,
    still-valid campaign worktree — just not THIS one — is refused."""
    work, _ = git_origin_repo
    foreign_root = run_setup_iterate_worktree(
        work, "campaign-other-campaign", "iterate-campaign-other-campaign")["project_root"]

    result = _location(foreign_root, "demo")
    assert result.returncode == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "demo" in payload["detail"]
