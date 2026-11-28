"""A phase that waits for an outside event (U5, campaign dfp-changelog-followups).

A changelog phase-runner result with ``waiting: {reason: waiting_for_merge, pr_url}`` leaves
the task in_progress (not done, not failed), plans no successor (deploy not scheduled), keeps
the run non-complete, makes ``single-session-next`` answer ``waiting`` with the link, and on a
confirmed resume the same task is dispatched again; a later ``ok`` result moves on as today.
The driven runs here are real run_configs walked through ``phase_task_lifecycle`` up to the
changelog task, then through the loop.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
sys.path.insert(0, str(_LIB))

from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg.single_session_recovery import resume_run  # noqa: E402
from phase_task_lifecycle import (  # noqa: E402
    claim_phase_task, complete_phase_task, freeze_splits, recover_phase_task,
)
from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    load_loop_state, record_gate_terminal, save_loop_state,
)
from single_session.result_contract import (  # noqa: E402
    build_phase_runner_result, validate_phase_runner_result,
)

PR = "https://github.com/acme/app/pull/42"
_HOOK = Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "master_stop_check.py"


def _cfg(root: Path) -> dict:
    return json.loads((root / "shipwright_run_config.json").read_text("utf-8"))


def _waiting(pr_url: str = PR, phase: str = "changelog") -> dict:
    return build_phase_runner_result(
        ok=False, phase=phase, summary="release PR open; waiting for its merge",
        artifacts=[], reason="waiting_for_merge",
        waiting={"reason": "waiting_for_merge", "pr_url": pr_url})


def _ok(phase: str = "changelog") -> dict:
    return build_phase_runner_result(ok=True, phase=phase, summary=f"{phase} done", artifacts=[])


def _run_to_changelog(root: Path, *, deploy_target: str = "jelastic-dev") -> None:
    """A real single_session run whose frontier is the changelog task."""
    create_config("full_app", "python-plugin-monorepo", "guided", deploy_target, root,
                  mode="single_session")
    freeze_splits(root)
    for phase in ["project", "design", "plan", "build", "test"]:
        cur = next(t for t in _cfg(root)["phase_tasks"]
                   if t["phase"] == phase and t["status"] == "awaiting_launch")
        claimed = claim_phase_task(root, phase_task_id=cur["phaseTaskId"],
                                   session_uuid=cur["sessionUuid"], expected_phase=phase)
        assert claimed["ok"], claimed
        done = complete_phase_task(root, phase_task_id=cur["phaseTaskId"],
                                   session_uuid=cur["sessionUuid"],
                                   expected_version=claimed["phase_task"]["version"],
                                   result={"ok": True})
        assert done["ok"], done


def _dispatch(root: Path) -> dict:
    nxt = loop.next_dispatch(root)
    assert nxt["action"] == "dispatch", nxt
    return nxt["dispatch"]


def _apply(root: Path, d: dict, result: dict) -> dict:
    return loop.apply_phase_result(root, phase_task_id=d["phaseTaskId"],
                                   session_uuid=d["sessionUuid"], expected_version=d["version"],
                                   result=result, enforce_gate=False)


def _wait(root: Path) -> tuple[dict, dict]:
    d = _dispatch(root)
    assert d["phase"] == "changelog"
    return d, _apply(root, d, _waiting())


# --------------------------------------------------------------------------- #
# the result contract
# --------------------------------------------------------------------------- #

@pytest.mark.covers("FR-01.01/AC39")
def test_contract_accepts_a_changelog_waiting_result():
    assert validate_phase_runner_result(_waiting()) == []


@pytest.mark.parametrize("bad, needle", [
    ({"ok": True}, "ok=False"),
    ({"waiting": {"reason": "waiting_for_review", "pr_url": PR}}, "waiting.reason"),
    ({"waiting": {"reason": "waiting_for_merge", "pr_url": "http://x/pull/1"}}, "pr_url"),
    ({"waiting": {"reason": "waiting_for_merge", "pr_url": PR + " rm"}}, "pr_url"),
    ({"waiting": {"reason": "waiting_for_merge", "pr_url": PR + "\x1b[2J"}}, "pr_url"),
    ({"waiting": {"reason": "waiting_for_merge", "pr_url": "https://" + "a" * 501}}, "pr_url"),
    ({"waiting": {"reason": "waiting_for_merge", "pr_url": "https:///pull/42"}}, "pr_url"),
    ({"waiting": {"reason": "waiting_for_merge", "pr_url": "https://"}}, "pr_url"),
    ({"waiting": {"reason": "waiting_for_merge"}}, "pr_url"),
    ({"waiting": "merge"}, "'waiting' must be a dict"),
    ({"phase": "build"}, "only the ('changelog',) phase"),
])
def test_contract_refuses_a_malformed_waiting_result(bad, needle):
    result = {**_waiting(), **bad}
    errors = validate_phase_runner_result(result)
    assert any(needle in e for e in errors), errors


def test_contract_refuses_a_waiting_reason_without_the_block():
    """A runner that only says reason=waiting_for_merge would be strict-stopped as failed."""
    result = {"ok": False, "phase": "changelog", "summary": "s", "artifacts": [],
              "reason": "waiting_for_merge"}
    assert any("needs the 'waiting' block" in e for e in validate_phase_runner_result(result))


# --------------------------------------------------------------------------- #
# apply / next / resume — the loop
# --------------------------------------------------------------------------- #

@pytest.mark.covers("FR-01.01/AC39")
def test_waiting_result_holds_the_task_and_schedules_nothing(tmp_project):
    _run_to_changelog(tmp_project)
    d, applied = _wait(tmp_project)

    assert applied["ok"] is True and applied["waiting"] == {"reason": "waiting_for_merge",
                                                            "pr_url": PR}
    cfg = _cfg(tmp_project)
    task = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == d["phaseTaskId"])
    assert task["status"] == "in_progress"          # not done, not failed
    assert cfg["status"] not in ("complete", "failed")
    assert not any(t["phase"] == "deploy" for t in cfg["phase_tasks"])  # deploy not scheduled
    nxt = applied["next"]
    assert nxt["action"] == "waiting" and nxt["pr_url"] == PR
    assert nxt["task"]["phaseTaskId"] == d["phaseTaskId"]
    assert PR in nxt["next_step"] and "Resume" in nxt["next_step"]
    # no completion telemetry: a waiting phase is neither a result nor a strict-stop
    kinds = [e["event"] for e in obs.load_events(tmp_project)]
    assert "phase_waiting" in kinds and "phase_result" not in kinds and "strict_stop" not in kinds


@pytest.mark.covers("FR-01.01/AC39")
def test_next_keeps_answering_waiting_until_resume_then_redispatches_the_same_task(tmp_project):
    _run_to_changelog(tmp_project)
    d, _ = _wait(tmp_project)

    for _ in range(2):  # stable: next never claims while held
        assert loop.next_dispatch(tmp_project)["action"] == "waiting"

    card = resume_run(tmp_project)
    assert card["action"] == "resume" and card["confirmed"] is False
    assert card["waiting"]["pr_url"] == PR and card["next"]["action"] == "waiting"
    assert set(card["waiting"]) == {"reason", "pr_url", "task", "next_step"}
    assert loop.next_dispatch(tmp_project)["action"] == "waiting"  # the card claims nothing

    confirmed = resume_run(tmp_project, confirm=True)
    assert confirmed["action"] == "resume" and confirmed["next"]["action"] == "dispatch"
    assert confirmed["waiting"] == card["waiting"]  # the same block, confirmed or not
    assert load_loop_state(tmp_project)["waiting"]["released"] is True

    again = _dispatch(tmp_project)
    assert again["phaseTaskId"] == d["phaseTaskId"] and again["version"] != d["version"]


@pytest.mark.covers("FR-01.01/AC39")
def test_ok_after_waiting_moves_on_to_deploy(tmp_project):
    _run_to_changelog(tmp_project)
    _wait(tmp_project)
    resume_run(tmp_project, confirm=True)
    d = _dispatch(tmp_project)
    applied = _apply(tmp_project, d, _ok())
    assert applied["ok"] and applied["next"]["action"] == "dispatch"
    assert applied["next"]["dispatch"]["phase"] == "deploy"


@pytest.mark.covers("FR-01.01/AC39")
def test_ok_after_waiting_ends_the_run_without_a_deploy_target(tmp_project):
    _run_to_changelog(tmp_project, deploy_target="none")
    _wait(tmp_project)
    assert _cfg(tmp_project)["status"] != "complete"
    resume_run(tmp_project, confirm=True)
    applied = _apply(tmp_project, _dispatch(tmp_project), _ok())
    assert applied["run_status"] == "complete" and applied["next"]["action"] == "complete"
    assert load_loop_state(tmp_project)["status"] == "complete"


@pytest.mark.covers("FR-01.01/AC39")
def test_a_late_waiting_result_from_an_older_dispatch_writes_nothing(tmp_project):
    _run_to_changelog(tmp_project)
    old = _dispatch(tmp_project)
    _dispatch(tmp_project)  # a second next rotates the version
    applied = _apply(tmp_project, old, _waiting())
    assert applied["ok"] is False and applied["reason"] == "stale_version"
    assert "waiting" not in (load_loop_state(tmp_project) or {})
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "dispatch"


def test_a_replayed_waiting_result_cannot_undo_a_confirmed_resume(tmp_project):
    """Resume released the hold of dispatch d; d's waiting result, applied again before the
    next dispatch, is refused and the next call still dispatches the same task."""
    _run_to_changelog(tmp_project)
    d, _ = _wait(tmp_project)
    resume_run(tmp_project, confirm=True)
    replay = _apply(tmp_project, d, _waiting())
    assert replay["ok"] is False and replay["reason"] == "stale_version"
    again = _dispatch(tmp_project)
    assert again["phaseTaskId"] == d["phaseTaskId"]


def test_an_unreadable_loop_state_fails_the_waiting_apply_closed(tmp_project):
    _run_to_changelog(tmp_project)
    d = _dispatch(tmp_project)
    path = tmp_project / ".shipwright" / "run_loop_state.json"
    path.write_text("{not json", encoding="utf-8")
    applied = _apply(tmp_project, d, _waiting())
    assert applied["ok"] is False and applied["reason"] == "loop_state_unreadable"
    assert path.read_text(encoding="utf-8") == "{not json"  # nothing written
    task = next(t for t in _cfg(tmp_project)["phase_tasks"] if t["phaseTaskId"] == d["phaseTaskId"])
    assert task["status"] == "in_progress"


def test_waiting_refuses_an_override_and_a_task_that_is_not_open(tmp_project):
    _run_to_changelog(tmp_project)
    d = _dispatch(tmp_project)
    refused = loop.apply_phase_result(
        tmp_project, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=_waiting(), override_reason="ship it")
    assert refused["ok"] is False and refused["reason"] == "override_requires_ok_result"
    assert _apply(tmp_project, d, _ok())["ok"]                  # the task is done now
    late = _apply(tmp_project, d, _waiting())
    assert late["ok"] is False


def test_recover_makes_the_hold_stale(tmp_project):
    _run_to_changelog(tmp_project)
    d, _ = _wait(tmp_project)
    assert recover_phase_task(tmp_project, phase_task_id=d["phaseTaskId"])["ok"]
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "dispatch"


def test_a_gate_decision_for_a_person_comes_before_the_hold(tmp_project):
    _run_to_changelog(tmp_project)
    d, _ = _wait(tmp_project)
    state = load_loop_state(tmp_project)
    save_loop_state(tmp_project, record_gate_terminal(
        state, phase_task_id=d["phaseTaskId"], version=d["version"], issues=[]))
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "ask_human"


def test_waiting_resets_the_retry_count(tmp_project):
    """A waiting pass is a finished pass: the re-dispatch does not eat the gate retry budget."""
    _run_to_changelog(tmp_project)
    _dispatch(tmp_project)
    d = _dispatch(tmp_project)  # attempt 2
    assert load_loop_state(tmp_project)["attempt"] == 2
    _apply(tmp_project, d, _waiting())
    assert load_loop_state(tmp_project)["attempt"] == 0
    resume_run(tmp_project, confirm=True)
    _dispatch(tmp_project)
    assert load_loop_state(tmp_project)["attempt"] == 1


# --------------------------------------------------------------------------- #
# the CLI and the master's Stop hook
# --------------------------------------------------------------------------- #

def _orchestrator(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_LIB / "orchestrator.py"), *args, "--project-root", str(root)],
        capture_output=True, text=True, encoding="utf-8", timeout=120)


@pytest.mark.covers("FR-01.01/AC39")
def test_cli_apply_and_next_exit_zero_for_waiting(tmp_project):
    _run_to_changelog(tmp_project)
    d = _dispatch(tmp_project)
    path = tmp_project / "result.json"
    path.write_text(json.dumps(_waiting()), encoding="utf-8")
    applied = _orchestrator(tmp_project, "single-session-apply", "--phase-task-id",
                            d["phaseTaskId"], "--session-uuid", d["sessionUuid"],
                            "--version", str(d["version"]), "--result-json", str(path))
    assert applied.returncode == 0, applied.stderr
    nxt = _orchestrator(tmp_project, "single-session-next")
    assert nxt.returncode == 0 and json.loads(nxt.stdout)["action"] == "waiting"


def _stop_banner(root: Path) -> str:
    out = subprocess.run([sys.executable, str(_HOOK)], capture_output=True, text=True,
                         encoding="utf-8", env={**__import__("os").environ,
                                                "SHIPWRIGHT_PROJECT_ROOT": str(root), "PYTHONIOENCODING": "utf-8"},
                         timeout=60)
    assert out.returncode == 0
    return out.stderr


@pytest.mark.covers("FR-01.01/AC39")
def test_stop_hook_names_the_waiting_pull_request(tmp_project):
    _run_to_changelog(tmp_project)
    d, _ = _wait(tmp_project)
    banner = _stop_banner(tmp_project)
    assert "PIPELINE WAITING" in banner and PR in banner
    assert "--force-status failed" in banner  # the closed-without-merge escape

    # a hand-edited link with an escape sequence never reaches the terminal
    state = load_loop_state(tmp_project)
    state["waiting"]["prUrl"] = PR + "\x1b[2J"
    save_loop_state(tmp_project, state)
    banner = _stop_banner(tmp_project)
    assert "PIPELINE WAITING" in banner and "\x1b" not in banner

    # a stale hold (the task was recovered) is not reported
    recover_phase_task(tmp_project, phase_task_id=d["phaseTaskId"])
    assert "PIPELINE WAITING" not in _stop_banner(tmp_project)
