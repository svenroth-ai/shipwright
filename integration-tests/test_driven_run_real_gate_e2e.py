"""End to end: a deliberately broken artifact stops a DRIVEN run, and passes once fixed (A5).

The phase gate is enforced by default, so nothing here turns it on: every phase goes through
the real orchestrator CLI (``single-session-next`` / ``single-session-apply``, subprocesses,
the surface the master drives) over the real phase validators and canon checks, with the
test playing an honest phase-runner (``shared/testkit/minimal_valid_project``).

The planted defect is in the DESIGN phase, mid-pipeline: the design manifest names a screen
that was never written. Every retry goes through ``single-session-next`` (the only way a
retry is counted), so the cap is reached and the terminal for the run's autonomy is taken:

    guided      apply keeps rejecting (non-mutating); the last answer is ``ask_human`` and
                the task is still in progress; fixing the artifact lets the same task pass
    autonomous  the capped rejection strict-stops the task (``mark_phase_failed``: run failed,
                no successor); ``single-session-recover`` re-opens it, the fixed artifact passes

Either way the run then drives on to ``complete``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py")
sys.path.insert(0, str(REPO_ROOT / "shared" / "testkit"))
import minimal_valid_project as mvp  # noqa: E402

pytestmark = [pytest.mark.integration, pytest.mark.covers("FR-01.01/AC02")]

MAX_GATE_RETRIES = 2  # single_session.loop_state's; every rejection reports it (asserted)
_MANIFEST = Path(".shipwright/designs/design-manifest.md")
_BROKEN_ROW = "| 2 | screens/02-missing.html | FR-01.01 |\n"


def _cli(project: Path, *args: str) -> tuple[int, dict]:
    env = {k: v for k, v in os.environ.items() if k != "AIKIDO_CLIENT_ID"}
    proc = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project)],
        capture_output=True, text=True, encoding="utf-8", timeout=60, env=env,
    )
    assert proc.returncode in (0, 1, 2), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _start(tmp_path: Path, autonomy: str) -> Path:
    project = tmp_path / f"driven-{autonomy}"
    project.mkdir()
    code, cfg = _cli(project, "write-config", "--scope", "full_app", "--profile",
                     "supabase-nextjs", "--autonomy", autonomy, "--mode", "single_session")
    assert code == 0 and cfg["mode"] == "single_session"
    return project


def _next(project: Path, phase: str) -> dict:
    code, out = _cli(project, "single-session-next")
    assert code == 0 and out["action"] == "dispatch", out
    assert out["dispatch"]["phase"] == phase, out
    return out["dispatch"]


def _apply(project: Path, dispatch: dict, *, write: bool = True) -> tuple[int, dict]:
    split = dispatch.get("splitId")
    artifacts = (mvp.write_phase(project, dispatch["phase"], split) if write
                 else [_MANIFEST.as_posix()])
    payload = {"ok": True, "phase": dispatch["phase"], "summary": "done", "artifacts": artifacts}
    if split:
        payload["splitId"] = split
    result = project / f".result-{dispatch['phaseTaskId']}.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    return _cli(project, "single-session-apply", "--phase-task-id", dispatch["phaseTaskId"],
                "--session-uuid", dispatch["sessionUuid"], "--version", str(dispatch["version"]),
                "--result-json", str(result))


def _task(project: Path, phase_task_id: str) -> dict:
    cfg = json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    return next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == phase_task_id)


def _break_design(project: Path) -> tuple[dict, str]:
    """Drive project (passes), then a design whose manifest names a missing screen."""
    code, applied = _apply(project, _next(project, "project"))
    assert code == 0 and applied["gate"]["result"] == "pass", applied
    design = _next(project, "design")
    mvp.write_phase(project, "design")
    good = (project / _MANIFEST).read_text(encoding="utf-8")
    (project / _MANIFEST).write_text(good + _BROKEN_ROW, encoding="utf-8")
    return design, good


def _retry_until_terminal(project: Path, design: dict) -> list[dict]:
    """Apply the broken design at every dispatch, re-dispatching through
    ``single-session-next`` after each rejection, until the gate names a terminal."""
    answers: list[dict] = []
    dispatch = design
    for _ in range(MAX_GATE_RETRIES + 2):          # bounded: the cap must end this
        code, out = _apply(project, dispatch, write=False)
        answers.append(out)
        gate = out if out.get("reason") == "phase_gate_failed" else out.get("gate", {})
        assert any("02-missing.html" in i["message"] for i in gate["issues"]), out
        if gate["terminal"] is not None:
            return answers
        assert code == 1 and gate["retryable"] is True and out["ok"] is False
        assert _task(project, design["phaseTaskId"])["status"] == "in_progress"
        cfg = json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))
        assert design["phaseTaskId"] not in cfg["completed_phase_task_ids"]   # no completion
        assert not any(t["phase"] == "plan" for t in cfg["phase_tasks"])      # no successor
        dispatch = _next(project, "design")         # the counted retry, same task
        assert dispatch["phaseTaskId"] == design["phaseTaskId"]
    raise AssertionError(f"no terminal after {len(answers)} rejections: {answers[-1]}")


def _drive_to_complete(project: Path) -> None:
    for phase in ("plan", "build", "plan", "build", "test", "changelog", "deploy"):
        code, applied = _apply(project, _next(project, phase))
        assert code == 0 and applied["gate"]["result"] == "pass", applied
    code, out = _cli(project, "single-session-next")
    assert out["action"] == "complete", out


def test_guided_run_stops_at_the_broken_artifact_and_passes_when_fixed(tmp_path):
    project = _start(tmp_path, "guided")
    design, good = _break_design(project)

    answers = _retry_until_terminal(project, design)
    last = answers[-1]
    assert len(answers) == MAX_GATE_RETRIES + 1          # first try + MAX_GATE_RETRIES retries
    assert (last["ok"], last["reason"], last["max_gate_retries"]) == (
        False, "phase_gate_failed", MAX_GATE_RETRIES)
    assert (last["retries_exhausted"], last["terminal"]) == (True, "ask_human")
    assert last["override_allowed"] is True                # a human may still decide
    assert _task(project, design["phaseTaskId"])["status"] == "in_progress"

    (project / _MANIFEST).write_text(good, encoding="utf-8")   # the fix
    code, passed = _apply(project, design, write=False)
    assert code == 0 and passed["gate"]["result"] == "pass", passed
    assert _task(project, design["phaseTaskId"])["status"] == "done"
    _drive_to_complete(project)


def test_autonomous_run_fails_the_phase_at_the_cap_and_recovers_when_fixed(tmp_path):
    project = _start(tmp_path, "autonomous")
    design, good = _break_design(project)

    answers = _retry_until_terminal(project, design)
    out = answers[-1]
    assert len(answers) == MAX_GATE_RETRIES + 1
    assert out["ok"] is True and out["run_status"] == "failed", out   # the strict-stop
    assert out["gate"]["terminal"] == "failed" and out["gate"]["retries_exhausted"] is True
    assert out["gate"]["max_gate_retries"] == MAX_GATE_RETRIES
    assert _task(project, design["phaseTaskId"])["status"] == "failed"
    code, terminal = _cli(project, "single-session-next")
    assert terminal["action"] == "failed", terminal

    (project / _MANIFEST).write_text(good, encoding="utf-8")   # the fix
    code, recovered = _cli(project, "single-session-recover", "--phase-task-id",
                           design["phaseTaskId"])
    assert code == 0 and recovered["ok"] is True, recovered
    code, passed = _apply(project, _next(project, "design"), write=False)
    assert code == 0 and passed["gate"]["result"] == "pass", passed
    _drive_to_complete(project)
