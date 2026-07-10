"""phase_started emit for the single-session loop (B1 / M-Pre-1).

single_session is the default + sole mode: its phases run as phase-runner
subagents that do NOT fire the phase Stop/SessionStart hooks. So the durable
``phase_started`` event (concept §5a — WebUI PhaseRail per-phase durations) is
emitted at the ``single-session-next`` CLI boundary, where the master claims +
begins a phase. Exactly one per phase; a crash-resume re-dispatch (idempotent)
must not double-emit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg.single_session_cli import dispatch_single_session  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402


def _ss_config(project_root: Path):
    return create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        project_root, mode="single_session",
    )


def _next(project_root: Path) -> int:
    return dispatch_single_session(
        SimpleNamespace(command="single-session-next"), project_root,
    )


def _apply_ok(project_root: Path, dispatch: dict) -> dict:
    """Play the phase-runner: persist artifacts + apply an ok result."""
    phase = dispatch["phase"]
    result = build_phase_runner_result(
        ok=True, phase=phase, summary=f"{phase} done",
        artifacts=[f"artifacts/{phase}.md"], reason=None, split_id=dispatch["splitId"],
    )
    for rel in result["artifacts"]:
        p = project_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    if phase == "design":  # single-pass build: no splits
        (project_root / "shipwright_design_config.json").write_text(
            json.dumps({"splits": []}), encoding="utf-8",
        )
    return loop.apply_phase_result(
        project_root, phase_task_id=dispatch["phaseTaskId"],
        session_uuid=dispatch["sessionUuid"], expected_version=dispatch["version"],
        result=result,
    )


def _events_of_type(project_root: Path, event_type: str) -> list[dict]:
    path = project_root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    events = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    return [e for e in events if e.get("type") == event_type]


def _phase_started(project_root: Path) -> list[dict]:
    return _events_of_type(project_root, "phase_started")


def test_single_session_next_emits_phase_started(tmp_project):
    cfg = _ss_config(tmp_project)
    assert _next(tmp_project) == 0

    started = _phase_started(tmp_project)
    assert len(started) == 1
    ev = started[0]
    assert ev["phase"] == "project"
    detail = json.loads(ev["detail"])
    assert detail["runId"] == cfg["runId"]


def test_single_session_reclaim_does_not_double_emit(tmp_project):
    _ss_config(tmp_project)
    _next(tmp_project)
    _next(tmp_project)  # no apply between -> idempotent re-dispatch
    assert len(_phase_started(tmp_project)) == 1


def test_run_plugin_emitters_never_raise_on_subprocess_failure(monkeypatch, tmp_project):
    """The run-plugin phase emitters are best-effort: a spawn failure must be
    swallowed, never propagate into the CLI next/apply path (NEW-3). The shared
    twin (phase_event_emit) has its own such test — this pins the run-plugin
    subprocess emitter independently."""
    import subprocess

    from orchestrator_pkg import events

    def boom(*_a, **_k):
        raise OSError("cannot spawn")

    monkeypatch.setattr(subprocess, "run", boom)
    # Neither emitter may raise even though the subprocess spawn fails.
    events.record_phase_started(tmp_project, phase="build", phase_task_id="ptk-x", split_id=None)
    events.record_phase_end(tmp_project, phase="build", status="done",
                            phase_task_id="ptk-x", split_id=None)


def test_single_session_apply_emits_paired_phase_completed(tmp_project, capsys):
    """single-session-next (start) + single-session-apply (end) write a PAIRED
    phase_started + phase_completed to the tracked shipwright_events.jsonl —
    same runId/phase, started.ts <= completed.ts. This makes per-phase durations
    computable from the tracked log alone in the sole default mode (FIX 1)."""
    cfg = _ss_config(tmp_project)
    _next(tmp_project)
    dispatch = json.loads(capsys.readouterr().out)["dispatch"]

    result = build_phase_runner_result(
        ok=True, phase=dispatch["phase"], summary="project done",
        artifacts=[f"artifacts/{dispatch['phase']}.md"], reason=None,
        split_id=dispatch["splitId"],
    )
    for rel in result["artifacts"]:
        p = tmp_project / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    result_path = tmp_project / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    rc = dispatch_single_session(SimpleNamespace(
        command="single-session-apply", result_json=str(result_path),
        phase_task_id=dispatch["phaseTaskId"], session_uuid=dispatch["sessionUuid"],
        version=dispatch["version"],
    ), tmp_project)
    assert rc == 0

    started = _events_of_type(tmp_project, "phase_started")
    completed = _events_of_type(tmp_project, "phase_completed")
    assert len(started) == 1 and len(completed) == 1
    s, c = started[0], completed[0]
    assert s["phase"] == c["phase"] == "project"
    assert json.loads(s["detail"])["runId"] == json.loads(c["detail"])["runId"] == cfg["runId"]
    assert s["ts"] <= c["ts"]  # start precedes end


def test_single_session_full_walk_one_started_per_phase(tmp_project, capsys):
    """A full single-session walk emits exactly one phase_started per phase
    (AC1/AC2 — one per phase across a run, no cross-phase double-emit)."""
    _ss_config(tmp_project)
    dispatched: list[str] = []
    for _ in range(20):  # safety bound; the pipeline is 7 phases single-pass
        _next(tmp_project)
        out = json.loads(capsys.readouterr().out)
        if out["action"] != "dispatch":
            break
        dispatch = out["dispatch"]
        dispatched.append(dispatch["phase"])
        applied = _apply_ok(tmp_project, dispatch)
        assert applied["ok"], applied

    assert dispatched[:3] == ["project", "design", "plan"]  # real pipeline order
    started_phases = [e["phase"] for e in _phase_started(tmp_project)]
    # Exactly one phase_started per dispatched phase, same phases in order.
    assert started_phases == dispatched
