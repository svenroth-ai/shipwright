"""The phase-gate SEAM in single-session apply (campaign brief-driven-run-a-real-gates, A4).

Injected gates only. On by default (A5), off leaves apply unchanged; a failed gate is a
non-mutating rejection; a stale or double apply keeps its CAS / idempotent answer; the
retry cap ends in the per-autonomy terminal. Override + real validators: ``_override.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import phase_gate  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    MAX_GATE_RETRIES,
    gate_retries_exhausted,
    load_loop_state,
)
from single_session.result_contract import build_phase_runner_result  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC02")

ASK = {"severity": "ask", "message": "Missing spec.md for splits: 01-core. Continue?"}


def _config(root: Path, autonomy: str = "guided") -> dict:
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                        mode="single_session")
    if autonomy != "guided":
        path = root / "shipwright_run_config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["autonomy"] = autonomy
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return cfg


def _result(root: Path, phase: str = "project") -> dict:
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts" / f"{phase}.md").write_text(f"# {phase}\n", encoding="utf-8")
    return build_phase_runner_result(ok=True, phase=phase, summary=f"{phase} done",
                                     artifacts=[f"artifacts/{phase}.md"])


def _gate(ask=(), inform=(), checked=True, calls=None):
    def fn(project_root, step, *, split_id=None, run_id=None):
        if calls is not None:
            calls.append({"step": step, "split_id": split_id, "run_id": run_id})
        return list(ask), list(inform), checked
    return fn


def _never(*_a, **_k):
    raise AssertionError("the gate must not be called here")


def _apply(root, d, **kw):
    return loop.apply_phase_result(
        root, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=kw.pop("result", None) or _result(root), **kw,
    )


def _task(root, d):
    return phase_task_lifecycle.get_phase_task(root, d["phaseTaskId"])["phase_task"]


def _dispatch(root):
    nxt = loop.next_dispatch(root)
    assert nxt["action"] == "dispatch", nxt
    return nxt["dispatch"]


def test_enforcement_is_on_by_default(tmp_project):  # A5 flipped it
    assert phase_gate.ENFORCE_PHASE_GATE_DEFAULT is True
    _config(tmp_project)
    assert _apply(tmp_project, _dispatch(tmp_project), gate=_gate([ASK]))["reason"] == "phase_gate_failed"


def test_enforcement_off_never_calls_the_gate(tmp_project):
    """Off (``enforce_gate=False``): the gate is not called."""
    _config(tmp_project)
    applied = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=False, gate=_never)
    assert applied["ok"] is True
    assert set(applied) == {"ok", "completion", "run_status", "next"}  # no gate block


def test_a_failed_gate_changes_nothing_but_the_rejection_count(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    rc = tmp_project / "shipwright_run_config.json"
    before, loop_before = rc.read_bytes(), load_loop_state(tmp_project)

    applied = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))

    assert applied["ok"] is False and applied["reason"] == "phase_gate_failed"
    assert applied["issues"] == [ASK]
    assert (applied["attempt"], applied["terminal"], applied["retryable"]) == (1, None, True)
    assert applied["max_gate_retries"] == MAX_GATE_RETRIES
    assert rc.read_bytes() == before                      # run_config untouched
    after = {**load_loop_state(tmp_project), "updatedAt": None}
    assert after == {**loop_before, "updatedAt": None, "gateRejections": 1}
    assert _task(tmp_project, d)["status"] == "in_progress"


def test_a_passing_gate_completes_and_reports_what_ran(tmp_project):
    _config(tmp_project)
    applied = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True,
                     gate=_gate(inform=[{"severity": "inform", "message": "note"}]))
    assert applied["ok"] is True
    assert applied["gate"]["result"] == "pass"
    assert applied["gate"]["inform"][0]["message"] == "note"


def test_a_gate_with_no_validator_reports_not_checked(tmp_project):
    _config(tmp_project)
    applied = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True,
                     gate=_gate(checked=False))
    assert applied["ok"] is True and applied["gate"]["result"] == "not_checked"


def test_a_stale_apply_keeps_its_cas_answer(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    phase_task_lifecycle.recover_phase_task(tmp_project, phase_task_id=d["phaseTaskId"])
    applied = _apply(tmp_project, d, enforce_gate=True, gate=_never)
    assert applied["reason"] == "stale_version"


def test_a_double_apply_of_a_done_task_stays_idempotent(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    assert _apply(tmp_project, d, gate=_gate())["ok"] is True
    again = _apply(tmp_project, d, enforce_gate=True, gate=_never)
    assert again["ok"] is True and again["completion"]["idempotent"] is True


def test_a_failed_task_cannot_be_reapplied_to_done(tmp_project):
    """Root fix: an ok=True re-apply used to turn a failed task done, past gate and recover."""
    _config(tmp_project)
    d = _dispatch(tmp_project)
    phase_task_lifecycle.mark_phase_failed(
        tmp_project, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], error="boom",
    )
    applied = _apply(tmp_project, d, enforce_gate=True, gate=_never)
    assert applied["ok"] is False and applied["reason"] == "invalid_status_for_completion"
    assert _task(tmp_project, d)["status"] == "failed"


def _exhaust(root, autonomy, gate):
    _config(root, autonomy)
    for attempt in range(1, MAX_GATE_RETRIES + 1):
        rejected = _apply(root, _dispatch(root), enforce_gate=True, gate=gate)
        assert (rejected["attempt"], rejected["terminal"]) == (attempt, None)
    return _dispatch(root)


def test_guided_retries_stop_at_the_cap_and_ask_the_human(tmp_project):
    d = _exhaust(tmp_project, "guided", _gate(ask=[ASK]))
    final = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    assert final["ok"] is False and final["reason"] == "phase_gate_failed"
    assert final["retries_exhausted"] is True and final["terminal"] == "ask_human"
    assert final["attempt"] == MAX_GATE_RETRIES + 1
    assert _task(tmp_project, d)["status"] == "in_progress"   # still non-mutating


def test_autonomous_retries_stop_at_the_cap_and_fail_the_phase(tmp_project):
    d = _exhaust(tmp_project, "autonomous", _gate(ask=[ASK]))
    final = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    assert final["ok"] is True and final["run_status"] == "failed"   # strict-stop shape
    assert final["gate"]["terminal"] == "failed" and final["gate"]["issues"] == [ASK]
    assert final["next"]["action"] == "failed"
    task = _task(tmp_project, d)
    assert task["status"] == "failed"
    assert "phase_gate_failed after 3 dispatch(es)" in task["errors"][-1]
    assert ASK["message"] in task["errors"][-1]
    assert load_loop_state(tmp_project)["status"] == "failed"
    # Recoverable: single-session-recover re-opens it with a fresh attempt counter.
    from orchestrator_pkg.single_session_recovery import recover_single_session
    assert recover_single_session(tmp_project, phase_task_id=d["phaseTaskId"])["ok"] is True
    assert _dispatch(tmp_project)["phaseTaskId"] == d["phaseTaskId"]
    assert load_loop_state(tmp_project)["attempt"] == 1


@pytest.mark.parametrize("autonomy,terminal", [("unattended", "failed"), ("bogus", "ask_human")])
def test_each_autonomy_takes_its_terminal_after_the_cap(tmp_project, autonomy, terminal):
    d = _exhaust(tmp_project, autonomy, _gate(ask=[ASK]))
    final = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    got = final.get("terminal") or final.get("gate", {}).get("terminal")
    assert got == terminal


def test_a_degraded_canon_run_is_ask_and_not_retryable(tmp_project):
    _config(tmp_project)
    note = {"severity": "inform", "kind": "canon_degraded", "message": "[canon-degraded] x"}
    applied = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True,
                     gate=_gate(inform=[note]))
    assert applied["reason"] == "phase_gate_failed"
    assert applied["issues"] == [{**note, "severity": "ask"}] and applied["inform"] == []
    assert (applied["retryable"], applied["terminal"]) == (False, "ask_human")


def test_a_raising_gate_becomes_a_gate_error_issue(tmp_project):
    _config(tmp_project)

    def boom(*_a, **_k):
        raise RuntimeError("validator exploded")

    applied = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True, gate=boom)
    assert applied["issues"][0]["message"].startswith("[gate-error]")
    assert "validator exploded" in applied["issues"][0]["message"]
    assert applied["retryable"] is False


def test_the_gate_gets_the_task_split_and_the_config_run_id(tmp_project):
    cfg = _config(tmp_project)
    calls: list = []
    _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True, gate=_gate(calls=calls))
    assert calls == [{"step": "project", "split_id": None, "run_id": cfg["runId"]}]


@pytest.mark.parametrize("config", [{}, {"runId": None}, {"runId": ""}])
def test_the_run_id_is_forwarded_unchanged_never_coerced(tmp_project, config):
    """Absent -> None (env fallback); an explicit blank stays blank (ask-level in canon)."""
    calls: list = []
    task = {"phase": "plan", "splitId": "01-core"}
    phase_gate.evaluate_gate(tmp_project, task, config, gate=_gate(calls=calls))
    assert calls == [{"step": "plan", "split_id": "01-core", "run_id": config.get("runId")}]


def test_a_crash_inside_the_default_gate_is_not_retryable(tmp_project, mocker):
    _config(tmp_project)
    mocker.patch("phase_validators.validate_phase", side_effect=RuntimeError("bug"))
    applied = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True)
    assert applied["issues"][0]["message"].startswith("[gate-error]")
    assert (applied["retryable"], applied["terminal"]) == (False, "ask_human")


def test_without_loop_state_the_retry_position_is_unknown(tmp_project):
    cfg = _config(tmp_project)
    seed = cfg["phase_tasks"][0]
    phase_task_lifecycle.claim_phase_task(
        tmp_project, phase_task_id=seed["phaseTaskId"], session_uuid=seed["sessionUuid"],
        expected_phase="project",
    )
    d = {"phaseTaskId": seed["phaseTaskId"], "sessionUuid": seed["sessionUuid"],
         "version": seed.get("version", 1)}
    applied = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    assert (applied["attempt"], applied["terminal"]) == (None, None)
    assert applied["gate_rejections"] is None


def test_a_failed_terminal_that_loses_the_cas_race_reports_it(tmp_project, monkeypatch):
    d = _exhaust(tmp_project, "autonomous", _gate(ask=[ASK]))
    monkeypatch.setattr(phase_task_lifecycle, "mark_phase_failed",
                        lambda *_a, **_k: {"ok": False, "reason": "stale_version"})
    out = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    assert (out["ok"], out["reason"]) == (False, "stale_version")
    assert _task(tmp_project, d)["status"] == "in_progress"


def test_a_drifted_loop_pointer_restarts_the_count_for_the_claimed_task(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    path = tmp_project / ".shipwright" / "run_loop_state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**state, "currentPhaseTaskId": "ptk-other", "attempt": 7}),
                    encoding="utf-8")
    assert _dispatch(tmp_project)["phaseTaskId"] == d["phaseTaskId"]
    state = load_loop_state(tmp_project)
    assert (state["currentPhaseTaskId"], state["attempt"]) == (d["phaseTaskId"], 1)


def test_a_raising_completion_hook_writes_nothing(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    rc = tmp_project / "shipwright_run_config.json"
    before = rc.read_bytes()

    def hook(_config, _task):
        raise KeyError("nope")

    done = phase_task_lifecycle.complete_phase_task(
        tmp_project, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=_result(tmp_project), on_complete=hook,
    )
    assert done["ok"] is False and done["reason"] == "on_complete_failed"
    assert rc.read_bytes() == before


def test_the_cap_boundary():
    assert not gate_retries_exhausted(MAX_GATE_RETRIES)
    assert gate_retries_exhausted(MAX_GATE_RETRIES + 1)
