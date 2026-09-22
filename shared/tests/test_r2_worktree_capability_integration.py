"""Integration test (``category: "integration"``): R2's per-unit worktree
capability end to end — two sibling worktrees for the same campaign slug,
independent leases, a campaign-level tree op that must not cross into
either sibling, concurrent lease touches on one lock file, and the
session-id / lease-upsert edge cases the sub-iterate spec's own "Test
strategy" section names.

Lives under ``shared/tests`` (one-test-root-per-process rule) — every module
under test here (``lib.campaign_unit_worktree``, ``lib.unit_lease``,
``lib.campaign_session_lock``, ``lib.worktree_location``) is importable from
this root already, matching ``test_campaign_dag_integration.py``'s own
placement rationale.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from lib import campaign_session_lock as csl
from lib.campaign_unit_worktree import composite_worktree_name
from lib.unit_lease import touch_unit_lease
from lib.worktree_location import worktree_location_error


def _add_worktree(work: Path, dirname: str, branch: str) -> Path:
    wt = work / ".worktrees" / dirname
    subprocess.run(
        ["git", "-C", str(work), "worktree", "add", str(wt), "-b", branch, "main"],
        capture_output=True, text=True, check=True,
    )
    return wt


def _write_loop_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "r2-it", "units": units}), encoding="utf-8")


def test_two_sibling_per_unit_worktrees_are_independently_isolated(git_origin_repo):
    """Two units of the SAME campaign slug get distinct, sibling worktree
    directories, each passing the location+identity guard for its OWN unit
    id and failing it for the other's."""
    work, _ = git_origin_repo
    name_r2 = composite_worktree_name("dag-scheduler", "R2")
    name_r3 = composite_worktree_name("dag-scheduler", "R3")
    wt_r2 = _add_worktree(work, name_r2, "iterate/campaign-dag-scheduler--R2")
    wt_r3 = _add_worktree(work, name_r3, "iterate/campaign-dag-scheduler--R3")

    assert wt_r2 != wt_r3
    assert worktree_location_error(wt_r2, expected_campaign_slug="dag-scheduler--R2") == ""
    assert worktree_location_error(wt_r3, expected_campaign_slug="dag-scheduler--R3") == ""
    assert worktree_location_error(wt_r2, expected_campaign_slug="dag-scheduler--R3") != ""
    assert worktree_location_error(wt_r3, expected_campaign_slug="dag-scheduler--R2") != ""


_SETUP_UNIT_WORKTREE_CLI = (
    Path(__file__).resolve().parents[1] / "scripts" / "tools" / "setup_unit_worktree.py"
)


def test_two_units_created_through_the_actual_wrapper_are_independent(git_origin_repo):
    """The spec's own AC names the WRAPPER creating "two per-unit worktrees
    ... at sibling paths" — the sibling-independence test above exercises
    only the guard against hand-built `git worktree add` calls, never
    `setup_unit_worktree.py` itself (external code review, GLM, low). This
    drives the real production entry point for both units and re-asserts
    the same independence properties through it."""
    work, _ = git_origin_repo

    def _run(unit_id: str, run_id: str):
        env = os.environ.copy()
        env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
        return subprocess.run(
            [sys.executable, str(_SETUP_UNIT_WORKTREE_CLI),
             "--project-root", str(work), "--campaign-slug", "dag-scheduler",
             "--unit-id", unit_id, "--run-id", run_id],
            env=env, capture_output=True, text=True,
        )

    r2 = _run("R2", "iterate-20260922-r2-it")
    r3 = _run("R3", "iterate-20260922-r3-it")
    assert r2.returncode == 0, r2.stderr
    assert r3.returncode == 0, r3.stderr

    wt_r2 = Path(json.loads(r2.stdout)["project_root"])
    wt_r3 = Path(json.loads(r3.stdout)["project_root"])
    assert wt_r2 != wt_r3
    assert wt_r2.is_dir() and wt_r3.is_dir()
    assert worktree_location_error(wt_r2, expected_campaign_slug="dag-scheduler--R2") == ""
    assert worktree_location_error(wt_r3, expected_campaign_slug="dag-scheduler--R3") == ""


def test_campaign_level_git_clean_skips_both_sibling_worktrees(git_origin_repo):
    """Actually RUNS `git clean -xfd` in the MAIN tree (external code review,
    GLM + OpenAI, high/low — a prior version of this test only wrote marker
    files and never invoked git, so it would have passed even if `git clean`
    destroyed both siblings). Git treats a linked worktree directory as a
    nested repository and skips it by default — verified empirically
    (`git clean -xfd -n` prints "Would skip repository .worktrees/<name>")
    rather than assumed."""
    work, _ = git_origin_repo
    wt_r2 = _add_worktree(work, composite_worktree_name("dag-scheduler", "R2"),
                           "iterate/campaign-dag-scheduler--R2")
    wt_r3 = _add_worktree(work, composite_worktree_name("dag-scheduler", "R3"),
                           "iterate/campaign-dag-scheduler--R3")
    (wt_r2 / "r2-marker.txt").write_text("r2 own file", encoding="utf-8")
    (wt_r3 / "r3-marker.txt").write_text("r3 own file", encoding="utf-8")
    # Untracked main-tree noise `git clean` SHOULD remove, to prove the run
    # actually did something rather than being a no-op on an already-clean tree.
    (work / "campaign-scratch-noise.txt").write_text("noise", encoding="utf-8")

    result = subprocess.run(
        ["git", "-C", str(work), "clean", "-xfd"],
        capture_output=True, text=True, check=True,
    )
    assert "Skipping repository" in result.stdout
    assert not (work / "campaign-scratch-noise.txt").exists()  # clean DID run

    assert (wt_r2 / "r2-marker.txt").exists()
    assert (wt_r3 / "r3-marker.txt").exists()
    assert worktree_location_error(wt_r2, expected_campaign_slug="dag-scheduler--R2") == ""
    assert worktree_location_error(wt_r3, expected_campaign_slug="dag-scheduler--R3") == ""


def test_campaign_level_git_add_all_does_not_stage_sibling_content(git_origin_repo):
    """`git add -A` in the MAIN tree must not stage either sibling's files —
    real Shipwright repos gitignore `.worktrees/` at the root (verified: this
    repo's own `.gitignore` line 137) and the test replicates that same
    convention rather than assuming an un-configured fixture behaves the
    same way."""
    work, _ = git_origin_repo
    # CI has no global git identity configured for this throwaway repo (unlike
    # a dev machine's own global config) — `git commit` fails with exit 128
    # ("Please tell me who you are") without it. Mirrors git_origin_repo's own
    # fixture env, since this is the only test in this file that commits
    # outside that fixture's internal `_git` helper.
    commit_env = os.environ.copy()
    commit_env.update({
        "GIT_AUTHOR_NAME": "Iso Test", "GIT_AUTHOR_EMAIL": "iso@test.invalid",
        "GIT_COMMITTER_NAME": "Iso Test", "GIT_COMMITTER_EMAIL": "iso@test.invalid",
    })
    (work / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", ".gitignore"],
                    capture_output=True, text=True, check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-m", "gitignore .worktrees/"],
                    env=commit_env, capture_output=True, text=True, check=True)

    wt_r2 = _add_worktree(work, composite_worktree_name("dag-scheduler", "R2"),
                           "iterate/campaign-dag-scheduler--R2")
    (wt_r2 / "r2-marker.txt").write_text("r2 own file", encoding="utf-8")

    subprocess.run(["git", "-C", str(work), "add", "-A"],
                    capture_output=True, text=True, check=True)
    status = subprocess.run(
        ["git", "-C", str(work), "status", "--porcelain=v1"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "r2-marker" not in status
    assert ".worktrees" not in status


def test_leases_are_held_and_touched_independently_per_unit(tmp_path):
    state = tmp_path / "loop_state.json"
    _write_loop_state(state, [
        {"id": "R2", "status": "in_progress"},
        {"id": "R3", "status": "pending"},
    ])

    touch_unit_lease(state, "R2", worktree="/wt/r2", branch="iterate/x-r2", attempt=0)
    data = json.loads(state.read_text(encoding="utf-8"))
    r2 = next(u for u in data["units"] if u["id"] == "R2")
    r3 = next(u for u in data["units"] if u["id"] == "R3")
    assert r2["worktree"] == "/wt/r2"
    assert "worktree" not in r3  # R3's lease never touched, untouched by R2's

    touch_unit_lease(state, "R3", worktree="/wt/r3", branch="iterate/x-r3", attempt=0)
    data = json.loads(state.read_text(encoding="utf-8"))
    r2 = next(u for u in data["units"] if u["id"] == "R2")
    r3 = next(u for u in data["units"] if u["id"] == "R3")
    assert r2["worktree"] == "/wt/r2"  # unchanged by R3's own touch
    assert r3["worktree"] == "/wt/r3"


def test_n_concurrent_touches_against_one_lock_file_all_succeed(tmp_path):
    state = tmp_path / "loop_state.json"
    _write_loop_state(state, [{"id": "R2", "status": "in_progress"}])
    errors: list[Exception] = []

    def _touch(i: int) -> None:
        try:
            touch_unit_lease(state, "R2", worktree=f"/wt-{i}", branch=f"b-{i}")
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=_touch, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors
    data = json.loads(state.read_text(encoding="utf-8"))
    assert len(data["units"]) == 1


def test_lease_touch_upsert_against_a_row_with_no_lease_fields_yet(tmp_path):
    """Because R2 is independent of R1 in the DAG, a row is not guaranteed to
    already carry lease fields — the FIRST touch for a unit must create them
    without error (spec's own Test-strategy wording)."""
    state = tmp_path / "loop_state.json"
    _write_loop_state(state, [{"id": "R2", "status": "pending", "depends_on": []}])
    lease = touch_unit_lease(state, "R2", worktree="/wt", branch="b")
    assert lease["attempt"] == 0
    assert lease["lease_touched_at"] is not None


def test_wrong_session_id_is_rejected_by_campaign_lock_error(tmp_path, monkeypatch):
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    csl.acquire(tmp_path, session_id="orchestrator-session")

    monkeypatch.setattr(csl, "_now", lambda: 1010.0)
    with pytest.raises(csl.CampaignLockError):
        csl.touch(tmp_path, session_id="wrong-session")


_CHECK_UNIT_LEASE_CLI = (
    Path(__file__).resolve().parents[1] / "scripts" / "checks" / "check_unit_lease.py"
)
_CHECK_SESSION_LOCK_CLI = (
    Path(__file__).resolve().parents[1] / "scripts" / "checks" / "check_campaign_session_lock.py"
)


def test_a_simulated_lease_touch_failure_exits_1_with_parseable_json(tmp_path):
    """The runner-facing contract that makes warn-and-continue POSSIBLE: the
    CLI a runner actually shells out to must exit non-zero with a parseable
    JSON block payload on failure, never a raw traceback a caller's own
    `if rc != 0: log and continue` cannot even read (external code review,
    GLM + OpenAI, medium — a prior version of this test only asserted an
    in-process Python exception was catchable, which is true of nearly any
    function and proves nothing about the CLI contract the runner depends
    on)."""
    state = tmp_path / "loop_state.json"
    _write_loop_state(state, [{"id": "R2", "status": "in_progress"}])

    result = subprocess.run(
        [sys.executable, str(_CHECK_UNIT_LEASE_CLI), "touch",
         "--state", str(state), "--unit-id", "R2-does-not-exist",
         "--worktree", str(tmp_path), "--branch", "b", "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)  # must be valid JSON, not a traceback
    assert payload["decision"] == "block"


def test_a_simulated_session_lock_touch_failure_exits_1_with_parseable_json(tmp_path):
    """Same contract, for the campaign session-lock touch the runner ALSO
    shells out to at each step boundary — a wrong/stale `session_id` (lock
    reclaimed by another session) must be diagnosable by a caller parsing
    stdout, not a traceback."""
    csl.acquire(tmp_path, session_id="orchestrator-session")

    result = subprocess.run(
        [sys.executable, str(_CHECK_SESSION_LOCK_CLI), "touch",
         "--campaign-worktree", str(tmp_path), "--session-id", "wrong-session", "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert payload["reason"] == "refused"
