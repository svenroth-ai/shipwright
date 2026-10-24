"""Closing the ways round the v2 phase gate (A4 doubt/code review follow-ups).

The raw ``complete-phase-task`` is refused while the gate is enforced; the override is an
autonomy ALLOWLIST checked again on the locked config; gate rejections are counted durably
in loop state, so re-applying without ``single-session-next`` still reaches the cap; a loop
pointer at another task means "unknown" (no cap); critical-gate findings are not retried.
The canon verifiers' plugin-cache layouts: ``test_phase_gate_cache_layouts.py``.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import phase_gate  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg.critical_gates import _collect_critical_gate_issues  # noqa: E402
from orchestrator_pkg.router import dispatch_lifecycle  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    MAX_GATE_RETRIES,
    advance_pointer,
    gate_retries_exhausted,
    load_loop_state,
)
from single_session.result_contract import build_phase_runner_result  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC02")

ASK = {"severity": "ask", "message": "Sections not complete: 01. Continue?"}
WHY = "the reviewer confirmed the sections are deliberately deferred"


def _config(root: Path, autonomy: str = "guided") -> dict:
    cfg = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                        mode="single_session")
    if autonomy != "guided":
        path = root / "shipwright_run_config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["autonomy"] = autonomy
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return cfg


def _result(root: Path, ok: bool = True) -> dict:
    art = root / "artifacts" / "project.md"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text("# project\n", encoding="utf-8")
    return build_phase_runner_result(ok=ok, phase="project", summary="project done",
                                     artifacts=["artifacts/project.md"] if ok else [],
                                     **({} if ok else {"reason": "broke"}))


def _gate(ask=()):
    return lambda _root, _step, *, split_id=None, run_id=None: (list(ask), [], True)


def _dispatch(root):
    nxt = loop.next_dispatch(root)
    assert nxt["action"] == "dispatch", nxt
    return nxt["dispatch"]


def _apply(root, d, **kw):
    return loop.apply_phase_result(
        root, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=kw.pop("result", None) or _result(root), **kw,
    )


def _status(root, d):
    return phase_task_lifecycle.get_phase_task(root, d["phaseTaskId"])["phase_task"]["status"]


# --- 1. the raw complete-phase-task --------------------------------------------------

def _raw_complete(root, d, result, capsys):
    path = root / "result.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    args = argparse.Namespace(command="complete-phase-task", phase_task_id=d["phaseTaskId"],
                              session_uuid=d["sessionUuid"], version=d["version"],
                              result_json=str(path))
    code = dispatch_lifecycle(args, root)
    return code, json.loads(capsys.readouterr().out)


def test_raw_completion_is_refused_while_the_gate_is_enforced(tmp_project, monkeypatch, capsys):
    assert phase_gate.ENFORCE_PHASE_GATE_DEFAULT is True  # A5: on by default
    _config(tmp_project)
    d = _dispatch(tmp_project)
    code, out = _raw_complete(tmp_project, d, _result(tmp_project), capsys)
    assert (code, out["reason"]) == (2, "use_single_session_apply")
    assert "single-session-apply" in out["error"]
    assert _status(tmp_project, d) == "in_progress"
    # A strict-stop (ok:false) is never gated, so it still goes through.
    code, out = _raw_complete(tmp_project, d, _result(tmp_project, ok=False), capsys)
    assert code == 0 and _status(tmp_project, d) == "failed"


def test_raw_completion_is_unchanged_with_enforcement_off(tmp_project, monkeypatch, capsys):
    monkeypatch.setattr(phase_gate, "ENFORCE_PHASE_GATE_DEFAULT", False)
    _config(tmp_project)
    d = _dispatch(tmp_project)
    code, out = _raw_complete(tmp_project, d, _result(tmp_project), capsys)
    assert code == 0 and out["ok"] is True and _status(tmp_project, d) == "done"


# --- 2. the override allowlist ---------------------------------------------------------

@pytest.mark.covers("FR-01.01/AC03")
@pytest.mark.parametrize("raw", ["guided", "autonomous", " Guided ", "AUTONOMOUS"])
def test_an_override_is_allowed_only_for_a_listed_autonomy(raw):
    reason, refused = phase_gate.check_override({"autonomy": raw}, {"ok": True}, WHY)
    assert (reason, refused) == (WHY, None)


@pytest.mark.covers("FR-01.01/AC03")
@pytest.mark.parametrize("config", [{}, {"autonomy": None}, {"autonomy": ""},
                                    {"autonomy": "Unattended"}, {"autonomy": " unattended"},
                                    {"autonomy": "bogus"}, {"autonomy": 1}])
def test_an_override_is_refused_for_any_other_autonomy(config):
    reason, refused = phase_gate.check_override(config, {"ok": True}, WHY)
    assert reason is None and refused["reason"] == "override_requires_human"


@pytest.mark.covers("FR-01.01/AC03")
def test_the_override_records_the_raw_autonomy(tmp_project):
    _config(tmp_project, " Guided ")
    applied = _apply(tmp_project, _dispatch(tmp_project), override_reason=WHY,
                     gate=_gate(ask=[ASK]))
    assert applied["ok"] is True and applied["override"]["autonomy"] == " Guided "


@pytest.mark.covers("FR-01.01/AC03")
def test_the_hook_rechecks_the_autonomy_on_the_locked_config(tmp_project, monkeypatch):
    """The config apply read first said guided; the one under the lock says unattended."""
    _config(tmp_project, "unattended")
    d = _dispatch(tmp_project)
    monkeypatch.setattr(phase_gate, "check_override", lambda _c, _r, why: (why, None))
    rc = tmp_project / "shipwright_run_config.json"
    before = rc.read_bytes()
    applied = _apply(tmp_project, d, override_reason=WHY, gate=_gate(ask=[ASK]))
    assert (applied["ok"], applied["reason"]) == (False, "override_requires_human")
    assert rc.read_bytes() == before and _status(tmp_project, d) == "in_progress"


# --- 4/5. the durable count and the unknown position ---------------------------------

def test_reapplying_without_next_still_reaches_the_cap(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    for n in range(1, MAX_GATE_RETRIES + 1):
        rejected = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
        assert (rejected["attempt"], rejected["gate_rejections"], rejected["terminal"]) == (
            1, n, None)
    final = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    assert final["retries_exhausted"] is True and final["terminal"] == "ask_human"
    assert load_loop_state(tmp_project)["gateRejections"] == MAX_GATE_RETRIES + 1


def test_without_loop_state_there_is_no_cap(tmp_project):
    """Documented: a library apply with no single-session-next is never counted."""
    cfg = _config(tmp_project)
    seed = cfg["phase_tasks"][0]
    phase_task_lifecycle.claim_phase_task(
        tmp_project, phase_task_id=seed["phaseTaskId"], session_uuid=seed["sessionUuid"],
        expected_phase="project",
    )
    d = {"phaseTaskId": seed["phaseTaskId"], "sessionUuid": seed["sessionUuid"],
         "version": seed.get("version", 1)}
    for _ in range(MAX_GATE_RETRIES + 2):
        out = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
        assert (out["attempt"], out["gate_rejections"], out["terminal"]) == (None, None, None)
    assert load_loop_state(tmp_project) is None


@pytest.mark.parametrize("edit", [{"currentPhaseTaskId": "ptk-other"}, {"runId": "run-other"},
                                  {"attempt": "x"}, {"gateRejections": [1]}])
def test_a_loop_state_for_another_task_or_malformed_is_unknown(tmp_project, edit):
    cfg = _config(tmp_project)
    d = _dispatch(tmp_project)
    path = tmp_project / ".shipwright" / "run_loop_state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**state, **edit}), encoding="utf-8")
    assert phase_gate.retry_state(tmp_project, cfg, d["phaseTaskId"]) is None
    out = _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    assert (out["attempt"], out["terminal"]) == (None, None)


def test_an_unreadable_loop_state_is_unknown(tmp_project):
    cfg = _config(tmp_project)
    d = _dispatch(tmp_project)
    (tmp_project / ".shipwright" / "run_loop_state.json").write_text("{bad", encoding="utf-8")
    assert phase_gate.retry_state(tmp_project, cfg, d["phaseTaskId"]) is None


def test_the_rejection_count_resets_with_the_pointer(tmp_project):
    assert advance_pointer({"gateRejections": 2, "attempt": 3}, completed_phase_task_id="a",
                           next_phase_task_id="b")["gateRejections"] == 0
    _config(tmp_project)
    d = _dispatch(tmp_project)
    _apply(tmp_project, d, enforce_gate=True, gate=_gate(ask=[ASK]))
    from orchestrator_pkg.single_session_recovery import recover_single_session
    recovered = recover_single_session(tmp_project, phase_task_id=d["phaseTaskId"])
    assert recovered["ok"] is True
    assert load_loop_state(tmp_project)["gateRejections"] == 0


@pytest.mark.covers("FR-01.01/AC03")
@pytest.mark.parametrize("config,allowed", [
    ({"autonomy": "guided"}, True), ({"autonomy": " Autonomous"}, True), ({}, False),
    ({"autonomy": "unattended"}, False), ({"autonomy": "bogus"}, False)])
def test_a_rejection_says_whether_go_ahead_anyway_can_be_offered(config, allowed):
    rejected = phase_gate.rejection(config, {"ask": [ASK], "inform": [], "checked": True}, None)
    assert rejected["override_allowed"] is allowed


def test_the_cap_counts_dispatches_or_rejections():
    assert not gate_retries_exhausted(MAX_GATE_RETRIES)
    assert gate_retries_exhausted(MAX_GATE_RETRIES + 1)
    assert not gate_retries_exhausted(1, MAX_GATE_RETRIES - 1)
    assert gate_retries_exhausted(1, MAX_GATE_RETRIES)


def test_failure_error_never_prints_an_unknown_count():
    verdict = {"ask": [ASK, {"severity": "ask", "name": "W5 (workflow)"}]}
    assert "after 3 dispatch(es)" in phase_gate.failure_error(verdict, 3)
    text = phase_gate.failure_error(verdict, None)
    assert "dispatch count unknown" in text and "None" not in text
    assert "W5 (workflow)" in text


# --- 6. critical-gate findings ---------------------------------------------------------

def test_a_critical_gate_finding_is_not_retryable(tmp_project):
    issues = _collect_critical_gate_issues(
        {"workflow": [{"id": "W5", "status": "FAIL", "evidence": "no review"}]})
    assert issues and issues[0]["kind"] == "critical_gate"
    assert phase_gate.is_retryable({"ask": issues}) is False
    _config(tmp_project)
    out = _apply(tmp_project, _dispatch(tmp_project), enforce_gate=True, gate=_gate(issues))
    assert (out["retryable"], out["terminal"]) == (False, "ask_human")


# --- 7. the gate's per-call off switch is a test seam, never a production bypass -------

_REPO = Path(__file__).resolve().parents[3]


def test_no_shipped_code_switches_the_gate_off():
    """Only ``--override-reason`` (recorded) may complete a phase over the gate: a shipped
    caller passing ``enforce_gate=False`` would bypass it with no record, so no shipped call
    passes ``enforce_gate`` at all (the default is the only production value)."""
    roots = [_REPO / "shared" / "scripts", *(_REPO / "plugins").glob("*/scripts")]
    offenders = [
        str(path.relative_to(_REPO)) for root in roots for path in root.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.keyword) and node.arg == "enforce_gate"
        and not (isinstance(node.value, ast.Constant) and node.value.value is None)
    ]
    assert roots[1:], "no plugin scripts trees found: the scan would pass vacuously"
    assert offenders == []


def test_every_phase_a_driven_run_can_dispatch_has_a_validator():
    """Enforcing means checked: a pipeline phase with no validator would pass ``not_checked``."""
    from orchestrator_pkg.config_factory import PIPELINE_STEPS
    from phase_validators import _VALIDATORS
    assert set(PIPELINE_STEPS) <= set(_VALIDATORS), set(PIPELINE_STEPS) - set(_VALIDATORS)
