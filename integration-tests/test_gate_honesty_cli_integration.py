"""Through the real orchestrator CLI: the driven run's phase records say what happened.

Composes the lifecycle (claim / redispatch / complete / recover), the single-session loop,
the enforced real phase gate and the tracked event writer, each as the master drives them
(subprocesses, the test playing an honest phase-runner via ``shared/testkit``):

1. a phase whose gate passes leaves ``phase_tasks[].gate`` (result, run id, time);
2. a gate-rejected phase is re-dispatched with a NEW version, the first dispatch's late
   result is refused ``stale_version`` (exit 2) and changes nothing, the new one completes;
3. a forced skip needs ``--reason``, stores it and appends one ``phase_skipped`` event.
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

pytestmark = [pytest.mark.integration, pytest.mark.covers("FR-01.01/AC03")]

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


def _config(project: Path) -> dict:
    return json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))


def _task(project: Path, ptk: str) -> dict:
    return next(t for t in _config(project)["phase_tasks"] if t["phaseTaskId"] == ptk)


def _next(project: Path, phase: str) -> dict:
    code, out = _cli(project, "single-session-next")
    assert code == 0 and out["action"] == "dispatch" and out["dispatch"]["phase"] == phase, out
    return out


def _apply(project: Path, d: dict, artifacts: list[str]) -> tuple[int, dict]:
    result = project / f".result-{d['phaseTaskId']}-v{d['version']}.json"
    result.write_text(json.dumps({"ok": True, "phase": d["phase"], "summary": "done",
                                  "artifacts": artifacts}), encoding="utf-8")
    return _cli(project, "single-session-apply", "--phase-task-id", d["phaseTaskId"],
                "--session-uuid", d["sessionUuid"], "--version", str(d["version"]),
                "--result-json", str(result))


def test_pass_record_fencing_and_skip_reason_compose(tmp_path):
    project = tmp_path / "driven"
    project.mkdir()
    code, _ = _cli(project, "write-config", "--scope", "full_app", "--profile",
                   "supabase-nextjs", "--autonomy", "guided", "--mode", "single_session")
    assert code == 0

    # 1. project passes its real gate: the pass is now on the task, not only in stdout.
    p = _next(project, "project")["dispatch"]
    code, applied = _apply(project, p, mvp.write_phase(project, "project"))
    assert code == 0 and applied["gate"]["result"] == "pass", applied
    record = _task(project, p["phaseTaskId"])["gate"]
    assert (record["result"], record["phase"], record["overridden"]) == ("pass", "project", False)
    assert isinstance(record["runId"], str) and record["runId"] and record["at"]

    # 2. design: rejected, re-dispatched under a new version, stale result refused.
    first = _next(project, "design")["dispatch"]
    good_artifacts = mvp.write_phase(project, "design")
    good = (project / _MANIFEST).read_text(encoding="utf-8")
    (project / _MANIFEST).write_text(good + _BROKEN_ROW, encoding="utf-8")
    code, rejected = _apply(project, first, [_MANIFEST.as_posix()])
    assert code == 1 and rejected["reason"] == "phase_gate_failed", rejected

    again = _next(project, "design")
    second = again["dispatch"]
    assert again["idempotent"] is True and second["phaseTaskId"] == first["phaseTaskId"]
    assert second["version"] == first["version"] + 1

    (project / _MANIFEST).write_text(good, encoding="utf-8")   # the retry fixed it
    before = (project / "shipwright_run_config.json").read_bytes()
    code, stale = _apply(project, first, good_artifacts)
    assert code == 2 and stale["reason"] == "stale_version", stale
    assert (project / "shipwright_run_config.json").read_bytes() == before

    code, fresh = _apply(project, second, good_artifacts)
    assert code == 0 and fresh["gate"]["result"] == "pass", fresh
    assert _task(project, second["phaseTaskId"])["gate"]["result"] == "pass"

    # 3. plan: skipped by the operator — refused without a reason, recorded with one.
    plan = _next(project, "plan")["dispatch"]
    code, refused = _cli(project, "recover-phase-task", "--phase-task-id",
                         plan["phaseTaskId"], "--force-status", "skipped")
    assert code == 1 and refused["reason"] == "skip_reason_required"
    code, skipped = _cli(project, "recover-phase-task", "--phase-task-id",
                         plan["phaseTaskId"], "--force-status", "skipped",
                         "--reason", "planned by hand outside the run")
    assert code == 0 and skipped["phase_task"]["status"] == "skipped"
    assert _task(project, plan["phaseTaskId"])["skipReason"] == \
        "planned by hand outside the run"
    events = [json.loads(line) for line in
              (project / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    skips = [e for e in events if e["type"] == "phase_skipped"]
    assert len(skips) == 1 and skips[0]["phase"] == "plan"
    detail = json.loads(skips[0]["detail"])
    assert detail["reason"] == "planned by hand outside the run"
    assert detail["phaseTaskId"] == plan["phaseTaskId"] and detail["recoveredFrom"] == "in_progress"
