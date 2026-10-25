"""Re-dispatch rotates the phase task's CAS ``version`` (gate-honesty follow-ups).

A gate-rejected phase is retried by ``single-session-next``, which re-claims the SAME task
with the same ``sessionUuid``. The version used to stay put, so the earlier dispatch's
phase-runner result still passed the owner+version check after the phase was
re-dispatched. Every re-dispatch now bumps ``version``; only the newest descriptor applies.
These tests make the real stale apply and check that it changes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle as lc  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import cli as cli_mod  # noqa: E402
from orchestrator_pkg.completion_hook import completion_hook  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from single_session.loop_state import load_loop_state  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC02")

ASK = {"severity": "ask", "message": "Missing spec.md. Continue?"}
CONFIG = "shipwright_run_config.json"


def _config(root: Path) -> None:
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                  mode="single_session")


def _result(root: Path, phase: str = "project", ok: bool = True) -> dict:
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts" / f"{phase}.md").write_text(f"# {phase}\n", encoding="utf-8")
    return build_phase_runner_result(ok=ok, phase=phase, summary=f"{phase}",
                                     artifacts=[f"artifacts/{phase}.md"],
                                     reason=None if ok else "late failure")


def _gate(ask=(), hook=None):
    def fn(project_root, step, *, split_id=None, run_id=None):
        if hook is not None:
            hook()
        return list(ask), [], True
    return fn


def _dispatch(root: Path) -> dict:
    nxt = loop.next_dispatch(root)
    assert nxt["action"] == "dispatch", nxt
    return nxt


def _apply(root: Path, d: dict, phase: str = "project", ok: bool = True, **kw) -> dict:
    return loop.apply_phase_result(
        root, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=_result(root, phase, ok), **kw)


def _task(root: Path, ptk: str) -> dict:
    return lc.get_phase_task(root, ptk)["phase_task"]


def _rejected_then_redispatched(root: Path, phase: str = "project") -> tuple[dict, dict]:
    first = _dispatch(root)["dispatch"]
    rejected = _apply(root, first, phase, gate=_gate(ask=[ASK]))
    assert rejected["reason"] == "phase_gate_failed" and rejected["terminal"] is None
    second = _dispatch(root)
    assert second["idempotent"] is True
    return first, second["dispatch"]


def test_a_redispatch_rotates_the_version_and_nothing_else(tmp_project):
    _config(tmp_project)
    first = _dispatch(tmp_project)["dispatch"]
    before = _task(tmp_project, first["phaseTaskId"])
    second = _dispatch(tmp_project)
    after = _task(tmp_project, first["phaseTaskId"])
    assert second["idempotent"] is True
    assert second["dispatch"]["version"] == first["version"] + 1 == after["version"]
    assert second["dispatch"]["sessionUuid"] == first["sessionUuid"]
    assert after["executionCount"] == before["executionCount"]
    assert after["startedAt"] == before["startedAt"]  # the canon window opens at the claim
    assert after["redispatchedAt"] and after["status"] == "in_progress"


@pytest.mark.parametrize("ok", [True, False])
def test_the_first_dispatchs_late_result_is_refused_and_changes_nothing(tmp_project, ok):
    _config(tmp_project)
    first, second = _rejected_then_redispatched(tmp_project)
    config_before = (tmp_project / CONFIG).read_bytes()
    state_before = load_loop_state(tmp_project)

    stale = _apply(tmp_project, first, ok=ok, gate=_gate())
    assert stale["ok"] is False and stale["reason"] == "stale_version"
    assert (tmp_project / CONFIG).read_bytes() == config_before
    assert load_loop_state(tmp_project) == state_before

    fresh = _apply(tmp_project, second, gate=_gate())
    assert fresh["ok"] is True
    task = _task(tmp_project, second["phaseTaskId"])
    assert task["status"] == "done" and task["gate"]["result"] == "pass"


def test_the_stale_apply_exits_2_through_the_cli(tmp_project, monkeypatch, capsys):
    _config(tmp_project)
    first, _second = _rejected_then_redispatched(tmp_project)
    path = tmp_project / "stale.json"
    path.write_text(json.dumps(_result(tmp_project)), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "orchestrator.py", "single-session-apply", "--project-root", str(tmp_project),
        "--phase-task-id", first["phaseTaskId"], "--session-uuid", first["sessionUuid"],
        "--version", str(first["version"]), "--result-json", str(path)])
    assert cli_mod.main() == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "stale_version"
    assert _task(tmp_project, first["phaseTaskId"])["status"] == "in_progress"


def test_a_redispatch_landing_while_the_gate_runs_wins(tmp_project):
    """The race: the stale apply read a current task and is inside its gate when the
    re-dispatch commits. The completion re-checks the version under the lock."""
    _config(tmp_project)
    first = _dispatch(tmp_project)["dispatch"]
    stale = _apply(tmp_project, first, gate=_gate(hook=lambda: _dispatch(tmp_project)))
    assert stale["ok"] is False and stale["reason"] == "stale_version"
    task = _task(tmp_project, first["phaseTaskId"])
    assert task["status"] == "in_progress" and "gate" not in task
    assert task["version"] == first["version"] + 1


def test_a_stale_design_apply_does_not_refreeze_splits(tmp_project):
    _config(tmp_project)
    project = _dispatch(tmp_project)["dispatch"]
    assert _apply(tmp_project, project, enforce_gate=False)["ok"] is True
    first, _second = _rejected_then_redispatched(tmp_project, phase="design")
    assert first["phase"] == "design"
    before = (tmp_project / CONFIG).read_bytes()
    stale = _apply(tmp_project, first, phase="design", gate=_gate())
    assert stale["reason"] == "stale_version"
    assert (tmp_project / CONFIG).read_bytes() == before


def test_a_design_redispatch_landing_while_the_gate_runs_freezes_nothing(tmp_project):
    """The race the external code review named: the stale design apply was current when
    its gate started, the re-dispatch lands during the gate, and the freeze (in the completion lock) must
    then refuse under the lock instead of writing ``splits_frozen``."""
    _config(tmp_project)
    project = _dispatch(tmp_project)["dispatch"]
    assert _apply(tmp_project, project, enforce_gate=False)["ok"] is True
    (tmp_project / "shipwright_design_config.json").write_text(
        json.dumps({"splits": ["01-core", "02-api"]}), encoding="utf-8")
    first = _dispatch(tmp_project)["dispatch"]
    assert first["phase"] == "design"
    frozen_before = json.loads((tmp_project / CONFIG).read_text(encoding="utf-8")).get(
        "splits_frozen")

    stale = _apply(tmp_project, first, phase="design",
                   gate=_gate(hook=lambda: _dispatch(tmp_project)))
    assert stale["ok"] is False and stale["reason"] == "stale_version"
    cfg = json.loads((tmp_project / CONFIG).read_text(encoding="utf-8"))
    assert cfg.get("splits_frozen") == frozen_before != ["01-core", "02-api"]
    task = _task(tmp_project, first["phaseTaskId"])
    assert task["status"] == "in_progress" and "gate" not in task


@pytest.mark.parametrize("gated", [True, False], ids=["gated", "ungated"])
def test_a_current_design_apply_still_freezes_in_the_completion_write(tmp_project, gated):
    """The freeze follows the CAS (current, open task), not the gate: an ungated design
    completion (``enforce_gate=False``) freezes too (external code review, glm)."""
    _config(tmp_project)
    project = _dispatch(tmp_project)["dispatch"]
    assert _apply(tmp_project, project, enforce_gate=False)["ok"] is True
    (tmp_project / "shipwright_design_config.json").write_text(
        json.dumps({"splits": ["01-core"]}), encoding="utf-8")
    design = _dispatch(tmp_project)["dispatch"]
    applied = (_apply(tmp_project, design, phase="design", gate=_gate()) if gated
               else _apply(tmp_project, design, phase="design", enforce_gate=False))
    assert applied["ok"] is True
    cfg = json.loads((tmp_project / CONFIG).read_text(encoding="utf-8"))
    assert cfg["splits_frozen"] == ["01-core"]
    assert cfg["runConditions"]["splitMode"] == "per_split"
    design_task = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == design["phaseTaskId"])
    assert ("gate" in design_task) is gated


def test_the_completion_hook_freezes_in_place_and_a_refused_override_freezes_nothing():
    """The design freeze rides the completion's locked write (``completion_hook``): it is
    applied in place after the override, so a refusing override leaves the config untouched."""
    assert completion_hook(override=None, frozen_splits=None, verdict=None,
                           now=lambda: "t", freeze=lc.apply_frozen_splits) is None
    config, task = {"runConditions": {"autonomy": "guided"}}, {"phase": "design"}
    completion_hook(override=None, frozen_splits=["01-core"], verdict=None,
                    now=lambda: "t", freeze=lc.apply_frozen_splits)(config, task)
    assert config["splits_frozen"] == ["01-core"]
    assert config["runConditions"] == {"autonomy": "guided", "splitMode": "per_split"}
    assert "gate" not in task
    assert lc.apply_frozen_splits(config, []) == "none" and config["splits_frozen"] == []

    def refuse(_config, _task):
        raise RuntimeError("override refused")

    untouched: dict = {}
    with pytest.raises(RuntimeError):
        completion_hook(override=refuse, frozen_splits=["01-core"], verdict=None,
                        now=lambda: "t", freeze=lc.apply_frozen_splits)(untouched, task)
    assert untouched == {}


def test_a_recover_between_claim_and_rotation_records_no_dispatch(tmp_project, monkeypatch):
    _config(tmp_project)
    first = _dispatch(tmp_project)["dispatch"]
    attempt_before = load_loop_state(tmp_project)["attempt"]
    real_claim = lc.claim_phase_task

    def claim_then_recover(project_root, **kw):
        out = real_claim(project_root, **kw)
        lc.recover_phase_task(project_root, phase_task_id=kw["phase_task_id"])
        return out

    monkeypatch.setattr(lc, "claim_phase_task", claim_then_recover)
    nxt = loop.next_dispatch(tmp_project)
    assert nxt["action"] == "claim_failed" and nxt["reason"] == "invalid_status"
    assert load_loop_state(tmp_project)["attempt"] == attempt_before
    assert _task(tmp_project, first["phaseTaskId"])["status"] == "awaiting_launch"


def test_redispatch_refuses_an_unknown_task_or_a_foreign_claim(tmp_project):
    _config(tmp_project)
    first = _dispatch(tmp_project)["dispatch"]
    assert lc.redispatch_phase_task(tmp_project, phase_task_id="ptk-none",
                                    session_uuid="x")["reason"] == "not_found"
    foreign = lc.redispatch_phase_task(tmp_project, phase_task_id=first["phaseTaskId"],
                                       session_uuid="someone-else")
    assert foreign["reason"] == "stale_session"
    assert _task(tmp_project, first["phaseTaskId"])["version"] == first["version"]
