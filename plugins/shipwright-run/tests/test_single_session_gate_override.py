"""The v2 override and the REAL phase validators in single-session apply (A4).

``single-session-apply --override-reason`` runs the gate, then writes the override record and
the completion under one lock (``complete_phase_task(on_complete=...)``). The last tests run
the real ``project`` validator and its canon checks (no injected gate): a planted interview
transcript makes the grill-trace completeness gate run, a planted bad trace is rejected, and
the fixed trace passes.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import cli as cli_mod  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg.single_session_cli import dispatch_single_session  # noqa: E402
from orchestrator_pkg.validation_record import record_validation_override  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC03")

ASK = {"severity": "ask", "message": "Sections not complete: 01. Continue?"}
WHY = "the reviewer confirmed the sections are deliberately deferred"


def _config(root: Path, scope: str = "full_app", autonomy: str = "guided") -> dict:
    cfg = create_config(scope, "supabase-nextjs", "guided", "jelastic-dev", root,
                        mode="single_session")
    if autonomy != "guided":
        _edit_config(root, autonomy=autonomy)
    return cfg


def _edit_config(root: Path, **fields) -> None:
    path = root / "shipwright_run_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read(root: Path) -> dict:
    return json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))


def _result(root: Path, *, ok: bool = True, artifact: str = "artifacts/project.md") -> dict:
    if ok and not (root / artifact).exists():
        (root / artifact).parent.mkdir(parents=True, exist_ok=True)
        (root / artifact).write_text("# project\n", encoding="utf-8")
    return build_phase_runner_result(ok=ok, phase="project", summary="project",
                                     artifacts=[artifact], reason=None if ok else "broke")


def _gate(ask=(), calls=None):
    def fn(project_root, step, *, split_id=None, run_id=None):
        if calls is not None:
            calls.append(step)
        return list(ask), [], True
    return fn


def _dispatch(root):
    nxt = loop.next_dispatch(root)
    assert nxt["action"] == "dispatch", nxt
    return nxt["dispatch"]


def _apply(root, d, result=None, **kw):
    return loop.apply_phase_result(
        root, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=result or _result(root), **kw,
    )


@pytest.mark.parametrize("reason", ["", "   "])
def test_an_override_needs_a_reason(tmp_project, reason):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    before = (tmp_project / "shipwright_run_config.json").read_bytes()
    out = _apply(tmp_project, d, override_reason=reason, gate=_gate(ask=[ASK]))
    assert out["ok"] is False and out["reason"] == "override_reason_required"
    assert "--override-reason" in out["error"]
    assert (tmp_project / "shipwright_run_config.json").read_bytes() == before


def test_an_override_of_a_failed_phase_result_is_refused(tmp_project):
    _config(tmp_project)
    out = _apply(tmp_project, _dispatch(tmp_project), result=_result(tmp_project, ok=False),
                 override_reason=WHY)
    assert out["reason"] == "override_requires_ok_result"


def test_an_override_with_no_human_to_decide_is_refused(tmp_project):
    _config(tmp_project, autonomy="unattended")
    out = _apply(tmp_project, _dispatch(tmp_project), override_reason=WHY, gate=_gate([ASK]))
    assert out["reason"] == "override_requires_human"


def test_an_override_records_what_and_why_with_the_completion(tmp_project):
    _config(tmp_project, autonomy="autonomous")
    d = _dispatch(tmp_project)
    out = _apply(tmp_project, d, override_reason=f"  {WHY}  ", gate=_gate(ask=[ASK]))

    assert out["ok"] is True and out["gate"]["result"] == "fail"
    cfg = _read(tmp_project)
    [record] = cfg["validation_overrides"]
    assert record == out["override"]
    assert (record["reason"], record["waived"], record["gate_result"]) == (WHY, True, "fail")
    assert record["overridden_issues"] == [ASK]
    assert record["phase_task_id"] == d["phaseTaskId"] and "split_id" not in record
    assert (record["autonomy"], record["entrypoint"]) == ("autonomous", "single-session-apply")
    task = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == d["phaseTaskId"])
    assert task["status"] == "done"          # same write as the record


def test_an_override_runs_the_gate_even_with_enforcement_off(tmp_project):
    _config(tmp_project)
    calls: list = []
    out = _apply(tmp_project, _dispatch(tmp_project), override_reason=WHY,
                 enforce_gate=False, gate=_gate(calls=calls))
    assert calls == ["project"]
    assert out["override"]["gate_result"] == "pass" and out["override"]["waived"] is False


def test_a_double_apply_with_an_override_writes_no_second_record(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    assert _apply(tmp_project, d, override_reason=WHY, gate=_gate(ask=[ASK]))["ok"] is True
    again = _apply(tmp_project, d, override_reason="", gate=_gate(ask=[ASK]))
    assert again["ok"] is True and again["completion"]["idempotent"] is True
    assert again["override_skipped"] == "task_not_open" and "override" not in again
    assert len(_read(tmp_project)["validation_overrides"]) == 1


def test_a_stale_apply_with_an_override_keeps_its_cas_answer(tmp_project):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    phase_task_lifecycle.recover_phase_task(tmp_project, phase_task_id=d["phaseTaskId"])
    out = _apply(tmp_project, d, override_reason="", gate=_gate(ask=[ASK]))
    assert out["reason"] == "stale_version"
    assert "validation_overrides" not in _read(tmp_project)


def test_the_cli_passes_override_reason_through(tmp_project, capsys):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    result_path = tmp_project / "result.json"
    result_path.write_text(json.dumps(_result(tmp_project)), encoding="utf-8")
    args = cli_mod.build_parser().parse_args([
        "single-session-apply", "--phase-task-id", d["phaseTaskId"],
        "--session-uuid", d["sessionUuid"], "--version", str(d["version"]),
        "--result-json", str(result_path), "--override-reason", WHY,
    ])
    assert args.override_reason == WHY
    assert dispatch_single_session(args, tmp_project) == 0
    assert json.loads(capsys.readouterr().out)["override"]["reason"] == WHY
    assert _read(tmp_project)["validation_overrides"][0]["reason"] == WHY


def test_the_cli_refuses_a_blank_override_with_exit_1(tmp_project, capsys):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    result_path = tmp_project / "result.json"
    result_path.write_text(json.dumps(_result(tmp_project)), encoding="utf-8")
    args = argparse.Namespace(command="single-session-apply", phase_task_id=d["phaseTaskId"],
                              session_uuid=d["sessionUuid"], version=d["version"],
                              result_json=str(result_path), override_reason=" ")
    assert dispatch_single_session(args, tmp_project) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "override_reason_required"


def test_the_cli_refuses_completing_a_failed_task_with_exit_2(tmp_project, capsys):
    _config(tmp_project)
    d = _dispatch(tmp_project)
    phase_task_lifecycle.mark_phase_failed(
        tmp_project, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], error="boom",
    )
    result_path = tmp_project / "result.json"
    result_path.write_text(json.dumps(_result(tmp_project)), encoding="utf-8")
    args = argparse.Namespace(command="single-session-apply", phase_task_id=d["phaseTaskId"],
                              session_uuid=d["sessionUuid"], version=d["version"],
                              result_json=str(result_path))
    assert dispatch_single_session(args, tmp_project) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "invalid_status_for_completion"


def test_v1_records_a_degraded_canon_run_as_degraded_not_pass():
    note = {"severity": "inform", "kind": "canon_degraded", "message": "[canon-degraded] x"}
    cfg: dict = {}
    record = record_validation_override(cfg, "build", reason=WHY, ask_issues=[],
                                        inform_issues=[note])
    assert record["gate_result"] == "degraded" and record["waived"] is False
    assert not {"phase_task_id", "autonomy", "entrypoint"} & set(record)  # v1 shape


# --- the real project validator + canon checks, no injected gate -----------------------

_SPEC = (
    "## 2. Functional Requirements\n\n"
    "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
    "|---|---|---|---|---|---|---|\n"
    "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n\n"
    "### FR-01.01 — Login\n\n#### Acceptance Criteria\n"
    "- (E) Given a registered user, when they submit valid credentials, then they are signed in.\n"
)


def _trace(outcome: str) -> dict:
    dims = {d: "answered" for d in ("purpose", "boundaries", "failure", "out_of_scope")}
    return {
        "requirement_key": "login", "requirement_text": "The system SHALL sign users in.",
        "surface": "project", "evidence": ["turn 3: login is required"],
        "dimensions": {**dims, "outcome": outcome, "glossary": "n/a:no new term introduced",
                       "rationale": "n/a:not hard to reverse"},
        "fit_criterion": "a valid email/password pair signs the user in",
        "glossary_delta": [], "confirmed_by": "user confirmed in turn 5", "terms_used": [],
    }


def _minimal_project(root: Path) -> None:
    """An extension-scope project phase that passes every ERROR-level project check."""
    _config(root, scope="extension")

    def w(rel: str, text: str) -> None:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")

    w("shipwright_project_config.json",
      json.dumps({"status": "complete", "scope": "extension", "splits": [{"name": "01-core"}]}))
    w(".shipwright/planning/01-core/spec.md", _SPEC)
    w(".shipwright/agent_docs/decision_log.md",
      "# Decision Log\n\n### ADR-001: Project decomposition into splits\n\n**Status:** Accepted\n")
    w(".shipwright/agent_docs/build_dashboard.md", "# Dashboard\n\n- project: done\n")
    w("shipwright_events.jsonl", json.dumps({"type": "phase_completed", "event": "phase_completed",
                                             "phase": "project", "timestamp": "2026-10-24T00:00:00Z"}) + "\n")
    # The planted transcript: an interview ran, so the zero-traces check is live.
    w(".shipwright/planning/shipwright_project_interview.md", "# Interview\n")


def _write_trace(root: Path, outcome: str) -> None:
    path = root / ".shipwright" / "planning" / "grill-traces" / "login.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_trace(outcome)), encoding="utf-8")


def _real_apply(root: Path) -> dict:
    d = _dispatch(root)  # the phase records its history during ITS task, as the real skill does
    at = datetime.now(timezone.utc).isoformat()
    _edit_config(root, phase_history={"project": [{"run_id": _read(root)["runId"], "at": at,
                                                   "outcome": "complete"}]})
    return _apply(root, d, enforce_gate=True,
                  result=_result(root, artifact="shipwright_project_config.json"))


def test_the_zero_traces_check_runs_in_the_apply_path(tmp_project):
    _minimal_project(tmp_project)
    out = _real_apply(tmp_project)
    assert out["reason"] == "phase_gate_failed"
    assert [i["message"] for i in out["issues"] if "grill_trace_coverage" in i["message"]]
    assert all(i["message"].startswith("[canon]") for i in out["issues"])  # canon executed


def test_a_planted_bad_artifact_is_rejected_and_passes_when_fixed(tmp_project):
    _minimal_project(tmp_project)
    _write_trace(tmp_project, outcome="maybe")          # outside the closed vocabulary
    rejected = _real_apply(tmp_project)
    assert rejected["reason"] == "phase_gate_failed", rejected
    assert any("login" in i["message"] for i in rejected["issues"])

    _write_trace(tmp_project, outcome="answered")       # fixed
    passed = _real_apply(tmp_project)
    assert passed["ok"] is True, passed
    assert passed["gate"]["result"] == "pass"
    assert passed["completion"]["phase_task"]["status"] == "done"
