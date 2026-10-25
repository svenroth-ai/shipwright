"""A gated completion leaves a durable ``phase_tasks[].gate`` record (gate-honesty follow-ups).

Before, a phase whose gate PASSED left nothing in ``shipwright_run_config.json`` (the
``gate`` block was only in apply's stdout), so "passed its checks" could not be told from
"no check ran" afterwards. Now every gated completion — a pass, a not-checked pass, or
an override — writes what the gate said, for which phase/split, against which run id and
when, in the same locked write as the completion. Inform notes are counted, not stored.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle as lc  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC03")

ASK = {"severity": "ask", "message": "Missing spec.md. Continue?"}
NOTE = {"severity": "inform", "message": "consider a glossary"}
CONFIG = "shipwright_run_config.json"


def _config(root: Path) -> dict:
    return create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                         mode="single_session")


def _result(root: Path) -> dict:
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts" / "project.md").write_text("# project\n", encoding="utf-8")
    return build_phase_runner_result(ok=True, phase="project", summary="project done",
                                     artifacts=["artifacts/project.md"])


def _gate(ask=(), inform=(), checked=True, seen=None):
    def fn(project_root, step, *, split_id=None, run_id=None):
        if seen is not None:
            seen.append(run_id)
        return list(ask), list(inform), checked
    return fn


def _dispatch(root: Path) -> dict:
    nxt = loop.next_dispatch(root)
    assert nxt["action"] == "dispatch", nxt
    return nxt["dispatch"]


def _apply(root: Path, d: dict, **kw) -> dict:
    return loop.apply_phase_result(
        root, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=_result(root), **kw)


def _task(root: Path, d: dict) -> dict:
    return lc.get_phase_task(root, d["phaseTaskId"])["phase_task"]


def test_a_passing_gate_is_recorded_on_the_completed_task(tmp_project):
    cfg = _config(tmp_project)
    d = _dispatch(tmp_project)
    seen: list = []
    applied = _apply(tmp_project, d, gate=_gate(inform=[NOTE], seen=seen))
    assert applied["ok"] is True and applied["gate"]["result"] == "pass"

    record = _task(tmp_project, d)["gate"]
    at = record.pop("at")
    assert record == {"result": "pass", "checked": True, "phase": "project", "splitId": None,
                      "runId": cfg["runId"], "issueCount": 0, "informCount": 1,
                      "overridden": False}
    assert seen == [cfg["runId"]]  # the run id recorded is the one the gate was given
    assert datetime.fromisoformat(at).tzinfo is not None
    assert "consider a glossary" not in (tmp_project / CONFIG).read_text(encoding="utf-8")


def test_the_record_names_the_id_the_skill_minted_when_the_canon_check_used_it(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    path = tmp_project / CONFIG
    data = json.loads(path.read_text(encoding="utf-8"))
    data["phase_history"] = {"project": [{"run_id": "project-20261025-101500",
                                          "at": datetime.now(timezone.utc).isoformat()}]}
    path.write_text(json.dumps(data), encoding="utf-8")
    seen: list = []
    assert _apply(tmp_project, d, gate=_gate(seen=seen))["ok"] is True
    assert seen == ["project-20261025-101500"]
    assert _task(tmp_project, d)["gate"]["runId"] == "project-20261025-101500"


def test_a_gate_that_could_not_check_is_recorded_not_checked(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    assert _apply(tmp_project, d, gate=_gate(checked=False))["ok"] is True
    record = _task(tmp_project, d)["gate"]
    assert record["result"] == "not_checked" and record["checked"] is False


def test_an_override_is_recorded_on_the_task_beside_the_override_list(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    applied = _apply(tmp_project, d, gate=_gate(ask=[ASK]),
                     override_reason="deferred on purpose")
    assert applied["ok"] is True
    record = _task(tmp_project, d)["gate"]
    assert (record["result"], record["overridden"], record["issueCount"]) == ("fail", True, 1)
    overrides = json.loads((tmp_project / CONFIG).read_text(encoding="utf-8"))[
        "validation_overrides"]
    assert len(overrides) == 1 and overrides[0]["reason"] == "deferred on purpose"


def test_a_rejected_apply_writes_no_record(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    rejected = _apply(tmp_project, d, gate=_gate(ask=[ASK]))
    assert rejected["ok"] is False and rejected["reason"] == "phase_gate_failed"
    task = _task(tmp_project, d)
    assert task["status"] == "in_progress" and "gate" not in task


def test_an_ungated_completion_writes_no_record(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    assert _apply(tmp_project, d, enforce_gate=False)["ok"] is True
    assert "gate" not in _task(tmp_project, d)


def test_an_override_refused_on_the_locked_config_keeps_its_reason(tmp_project, monkeypatch):
    """The composed hook must not wrap the override's own refusal: the locked config losing
    its human still reads ``override_requires_human``, and nothing is recorded."""
    from orchestrator_pkg import phase_gate

    _config(tmp_project)
    d = _dispatch(tmp_project)
    real = phase_gate._human_can_override
    calls = {"n": 0}

    def flip(config):  # allowed at the pre-check, refused inside the locked hook
        calls["n"] += 1
        return real(config) if calls["n"] == 1 else False

    monkeypatch.setattr(phase_gate, "_human_can_override", flip)
    res = _apply(tmp_project, d, gate=_gate(ask=[ASK]), override_reason="why")
    assert res["ok"] is False and res["reason"] == "override_requires_human"
    assert "gate" not in _task(tmp_project, d)
