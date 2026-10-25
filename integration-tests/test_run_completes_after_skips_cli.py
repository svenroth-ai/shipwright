"""Through the real orchestrator CLI: skipping the last open task finishes a blocked run.

A driven run (subprocesses, real phase gates, ``shared/testkit`` playing an honest
phase-runner) reaches deploy; an earlier phase is re-opened while deploy is dispatched, so
deploy's completion parks the run in ``needs_validation``. The documented way out —
``recover-phase-task --force-status skipped --reason`` — now completes the run in the same
write, and ``single-session-next`` answers ``complete`` instead of ``needs_validation``
forever. The loop pointer is stamped ``complete`` too, and the skipped task stays skipped.
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

pytestmark = [pytest.mark.integration, pytest.mark.covers("FR-01.01/AC01")]


def _cli(project: Path, *args: str) -> tuple[int, dict]:
    env = {k: v for k, v in os.environ.items() if k != "AIKIDO_CLIENT_ID"}
    proc = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project)],
        capture_output=True, text=True, encoding="utf-8", timeout=60, env=env,
    )
    assert proc.returncode in (0, 1, 2), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _config(project: Path) -> dict:
    return json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))


def _next(project: Path, phase: str) -> dict:
    code, out = _cli(project, "single-session-next")
    assert code == 0 and out["action"] == "dispatch" and out["dispatch"]["phase"] == phase, out
    return out["dispatch"]


def _apply(project: Path, d: dict) -> tuple[int, dict]:
    split = d.get("splitId")
    payload = {"ok": True, "phase": d["phase"], "summary": "done",
               "artifacts": mvp.write_phase(project, d["phase"], split)}
    if split:
        payload["splitId"] = split
    result = project / f".result-{d['phaseTaskId']}-v{d['version']}.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    return _cli(project, "single-session-apply", "--phase-task-id", d["phaseTaskId"],
                "--session-uuid", d["sessionUuid"], "--version", str(d["version"]),
                "--result-json", str(result))


def test_skipping_the_last_open_task_completes_the_blocked_run(tmp_path):
    project = tmp_path / "driven"
    project.mkdir()
    code, _ = _cli(project, "write-config", "--scope", "full_app", "--profile",
                   "supabase-nextjs", "--autonomy", "guided", "--mode", "single_session")
    assert code == 0

    test_task = None
    for phase in ("project", "design", "plan", "build", "plan", "build", "test", "changelog"):
        d = _next(project, phase)
        test_task = d["phaseTaskId"] if phase == "test" else test_task
        code, applied = _apply(project, d)
        assert code == 0 and applied["gate"]["result"] == "pass", applied

    # deploy is dispatched; meanwhile the operator re-opens the test phase.
    deploy = _next(project, "deploy")
    code, reopened = _cli(project, "recover-phase-task", "--phase-task-id", test_task)
    assert code == 0 and reopened["phase_task"]["status"] == "awaiting_launch", reopened

    code, applied = _apply(project, deploy)
    assert code == 0 and applied["run_status"] == "needs_validation", applied
    code, blocked = _cli(project, "single-session-next")
    assert code == 0 and blocked["action"] == "needs_validation", blocked
    assert [b["phaseTaskId"] for b in blocked["blocked"]] == [test_task]

    code, skipped = _cli(project, "recover-phase-task", "--phase-task-id", test_task,
                         "--force-status", "skipped", "--reason", "tests ran outside the run")
    assert code == 0 and skipped["run_status"] == "complete", skipped

    code, done = _cli(project, "single-session-next")
    assert (code, done) == (0, {"action": "complete"})
    cfg = _config(project)
    assert cfg["status"] == "complete"
    task = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == test_task)
    assert (task["status"], task["skipReason"]) == ("skipped", "tests ran outside the run")
    loop = json.loads((project / ".shipwright" / "run_loop_state.json").read_text("utf-8"))
    assert loop["status"] == "complete"
