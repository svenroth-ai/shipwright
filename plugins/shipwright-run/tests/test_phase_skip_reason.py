"""A forced skip records WHY, on the task and as a durable event (gate-honesty follow-ups).

``recover-phase-task --force-status skipped`` used to flip the status and leave nothing
else: afterwards a skipped phase could not say why. Now the reason is required, stored
as ``skipReason`` and sent as one ``phase_skipped`` event to the tracked
``shipwright_events.jsonl`` — through both the generic and the in-loop recover CLI.
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
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from phase_task_recovery import MAX_SKIP_REASON_CHARS, normalise_skip_reason  # noqa: E402
from single_session.observability import load_events  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC03")

CONFIG = "shipwright_run_config.json"


def _project(root: Path) -> str:
    """A driven run with its first task dispatched (in_progress); returns its id."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                  mode="single_session")
    return loop.next_dispatch(root)["dispatch"]["phaseTaskId"]


def _task(root: Path, ptk: str) -> dict:
    return lc.get_phase_task(root, ptk)["phase_task"]


def _skip_events(root: Path) -> list[dict]:
    path = root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if r.get("type") == "phase_skipped"]


def _cli(monkeypatch, capsys, *argv: str) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", *argv])
    rc = cli_mod.main()
    return rc, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("reason", [None, "", "   ", "\n\t"])
def test_a_skip_without_a_reason_is_refused_and_writes_nothing(tmp_project, reason):
    ptk = _project(tmp_project)
    before = (tmp_project / CONFIG).read_bytes()
    res = lc.recover_phase_task(tmp_project, phase_task_id=ptk, force_status="skipped",
                                reason=reason)
    assert res["ok"] is False and res["reason"] == "skip_reason_required"
    assert "--reason" in res["blockMessage"]
    assert (tmp_project / CONFIG).read_bytes() == before
    assert _task(tmp_project, ptk)["status"] == "in_progress"


def test_the_reason_is_stored_on_the_skipped_task_as_one_bounded_line(tmp_project):
    ptk = _project(tmp_project)
    res = lc.recover_phase_task(tmp_project, phase_task_id=ptk, force_status="skipped",
                                reason="  no UI in\nthis run\x1b[31m  ")
    assert res["ok"] is True
    task = _task(tmp_project, ptk)
    assert task["status"] == "skipped"
    assert task["skipReason"] == "no UI in this run [31m"
    assert ptk in json.loads((tmp_project / CONFIG).read_text(encoding="utf-8"))[
        "completed_phase_task_ids"]


def test_a_long_reason_is_capped():
    assert normalise_skip_reason("x" * 600) == "x" * MAX_SKIP_REASON_CHARS


def test_reopening_a_skipped_task_drops_its_skip_reason_and_any_gate_record(tmp_project):
    ptk = _project(tmp_project)
    assert lc.recover_phase_task(tmp_project, phase_task_id=ptk, force_status="skipped",
                                 reason="later")["ok"]
    path = tmp_project / CONFIG
    data = json.loads(path.read_text(encoding="utf-8"))
    for t in data["phase_tasks"]:
        if t["phaseTaskId"] == ptk:
            t["gate"] = {"result": "pass"}   # a record left by an earlier completion
            t["redispatchedAt"] = "2026-10-25T00:00:00+00:00"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert lc.recover_phase_task(tmp_project, phase_task_id=ptk)["ok"]
    task = _task(tmp_project, ptk)
    assert task["status"] == "awaiting_launch"
    assert not {"skipReason", "gate", "redispatchedAt"} & set(task)


def test_a_non_skip_recover_needs_no_reason(tmp_project):
    ptk = _project(tmp_project)
    res = lc.recover_phase_task(tmp_project, phase_task_id=ptk, force_status="failed")
    assert res["ok"] is True and "skipReason" not in res["phase_task"]


def test_recover_phase_task_cli_refuses_a_skip_without_reason(tmp_project, monkeypatch, capsys):
    ptk = _project(tmp_project)
    rc, out = _cli(monkeypatch, capsys, "recover-phase-task", "--project-root",
                   str(tmp_project), "--phase-task-id", ptk, "--force-status", "skipped")
    assert rc == 1 and out["reason"] == "skip_reason_required"
    assert _skip_events(tmp_project) == []


def test_recover_phase_task_cli_records_reason_and_one_event(tmp_project, monkeypatch, capsys):
    ptk = _project(tmp_project)
    rc, out = _cli(monkeypatch, capsys, "recover-phase-task", "--project-root",
                   str(tmp_project), "--phase-task-id", ptk, "--force-status", "skipped",
                   "--reason", "design not needed for a CLI tool")
    assert rc == 0 and out["phase_task"]["skipReason"] == "design not needed for a CLI tool"
    events = _skip_events(tmp_project)
    assert len(events) == 1
    detail = json.loads(events[0]["detail"])
    assert events[0]["phase"] == "project"
    assert detail == {"phaseTaskId": ptk, "splitId": None,
                      "runId": json.loads((tmp_project / CONFIG).read_text(
                          encoding="utf-8"))["runId"],
                      "reason": "design not needed for a CLI tool",
                      "recoveredFrom": "in_progress"}


def test_single_session_recover_cli_records_reason_event_and_loop_event(
        tmp_project, monkeypatch, capsys):
    ptk = _project(tmp_project)
    rc, out = _cli(monkeypatch, capsys, "single-session-recover", "--project-root",
                   str(tmp_project), "--phase-task-id", ptk, "--force-status", "skipped")
    assert rc == 1 and out["reason"] == "skip_reason_required"

    rc, out = _cli(monkeypatch, capsys, "single-session-recover", "--project-root",
                   str(tmp_project), "--phase-task-id", ptk, "--force-status", "skipped",
                   "--reason", "operator: out of budget")
    assert rc == 0 and out["recover"]["phase_task"]["skipReason"] == "operator: out of budget"
    events = _skip_events(tmp_project)
    assert len(events) == 1 and json.loads(events[0]["detail"])["reason"] == \
        "operator: out of budget"
    recovery = [e for e in load_events(tmp_project) if e["event"] == "recovery"]
    assert len(recovery) == 1
    assert recovery[0]["reason"] == "operator: out of budget"
    assert recovery[0]["forceStatus"] == "skipped"
