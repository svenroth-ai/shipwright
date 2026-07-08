"""Integration test: single-session KILL-AND-RESUME (Campaign 2026-07-07, SS5, AC1).

The composition proof for SS5's resumability: a real config on disk, a real chain of
orchestrator subprocess calls (the SAME surface the master invokes), a simulated master
death mid-phase, and a resume that replays IDEMPOTENTLY. It exercises the loop
(``single-session-next``/``-apply``) + the recovery entry points
(``single-session-resume``) + ``phase_task_lifecycle`` + ``loop_state`` + the
observability event log composing across a crash — the cross_component integration
coverage the F11 verifier recomputes from the diff (``category:"integration"`` in the
Test Completeness Ledger).

Scenario:
    1. ``single-session-next`` claims the project task (in_progress) + records a dispatch.
    2. MASTER DEATH — the apply never runs; the task is left claimed-but-unapplied on disk.
    3. ``single-session-resume`` (read-only) reports the run is resumable and emits nothing.
    4. ``single-session-resume --confirm`` records the resume commitment.
    5. ``single-session-next`` re-claims the SAME task IDEMPOTENTLY (executionCount is NOT
       double-bumped) and re-dispatches it.
    6. ``single-session-apply`` completes it; the loop advances to the next phase.
    7. The observability log carries the whole story: dispatch -> resume -> dispatch -> phase_result.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(
    REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py",
)


def _run_cli(args: list[str], project_root: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AIKIDO_CLIENT_ID", None)
    result = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project_root)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
    )
    if result.returncode not in (0, 1, 2):
        raise RuntimeError(
            f"Orchestrator CLI crashed: rc={result.returncode}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )
    return result


def _write_ss_config(project: Path) -> dict:
    res = _run_cli([
        "write-config", "--scope", "full_app", "--profile", "supabase-nextjs",
        "--autonomy", "guided", "--mode", "single_session",
    ], project)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _read_config(project: Path) -> dict:
    return json.loads((project / "shipwright_run_config.json").read_text("utf-8"))


def _task(project: Path, phase_task_id: str) -> dict:
    for t in _read_config(project).get("phase_tasks", []):
        if t["phaseTaskId"] == phase_task_id:
            return t
    raise AssertionError(f"no task {phase_task_id}")


def _events(project: Path) -> list[dict]:
    path = project / ".shipwright" / "run_loop_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]


def _persist_and_apply(project: Path, dispatch: dict) -> dict:
    phase = dispatch["phase"]
    artifact_rel = f"artifacts/{phase}.md"
    art = project / artifact_rel
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(f"# {phase}\n", encoding="utf-8")
    payload = {"ok": True, "phase": phase, "summary": f"{phase} done",
               "artifacts": [artifact_rel]}
    if dispatch.get("splitId"):
        payload["splitId"] = dispatch["splitId"]
    result_path = project / f".result-{dispatch['phaseTaskId']}.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    res = _run_cli([
        "single-session-apply",
        "--phase-task-id", dispatch["phaseTaskId"],
        "--session-uuid", dispatch["sessionUuid"],
        "--version", str(dispatch["version"]),
        "--result-json", str(result_path),
    ], project)
    return json.loads(res.stdout)


class TestKillAndResumeIdempotent:
    def test_dead_master_resumes_and_replays_idempotently(self, tmp_path):
        project = tmp_path / "ss-kill-resume"
        project.mkdir()
        cfg = _write_ss_config(project)
        run_id = cfg["runId"]

        # 1. next → claim the project task (in_progress) + dispatch event.
        nxt = json.loads(_run_cli(["single-session-next"], project).stdout)
        assert nxt["action"] == "dispatch"
        dispatch = nxt["dispatch"]
        assert dispatch["phase"] == "project"
        ptk = dispatch["phaseTaskId"]
        assert _task(project, ptk)["status"] == "in_progress"
        exec_count_after_first_claim = _task(project, ptk).get("executionCount")

        # 2. MASTER DEATH: no apply happens. State is left claimed-but-unapplied.

        # 3. resume (read-only): the run is resumable; emits nothing new.
        events_before_resume = _events(project)
        resume = json.loads(_run_cli(["single-session-resume"], project).stdout)
        assert resume["action"] == "resume"
        assert resume["resumeAction"] == "dispatch"  # the in_progress frontier
        assert resume["loopState"]["currentPhaseTaskId"] == ptk
        assert _events(project) == events_before_resume, "read-only resume must not emit"

        # 4. resume --confirm: record the commitment.
        confirmed = json.loads(
            _run_cli(["single-session-resume", "--confirm"], project).stdout
        )
        assert confirmed["confirmed"] is True

        # 5. next again → IDEMPOTENT re-claim of the SAME task (no double execution).
        nxt2 = json.loads(_run_cli(["single-session-next"], project).stdout)
        assert nxt2["action"] == "dispatch"
        dispatch2 = nxt2["dispatch"]
        assert dispatch2["phaseTaskId"] == ptk
        assert dispatch2["sessionUuid"] == dispatch["sessionUuid"]
        assert nxt2.get("idempotent") is True
        assert _task(project, ptk).get("executionCount") == exec_count_after_first_claim, \
            "re-claim on resume must NOT bump executionCount (idempotent replay)"

        # 6. apply → completes; the loop advances off the project phase.
        applied = _persist_and_apply(project, dispatch2)
        assert applied["ok"] is True
        assert _task(project, ptk)["status"] == "done"
        assert applied["next"]["action"] in ("dispatch", "complete", "needs_validation")

        # 7. the event log tells the whole story, in order.
        seq = [e["event"] for e in _events(project)]
        assert seq == ["dispatch", "resume", "dispatch", "phase_result"], seq
        assert all(e["runId"] == run_id for e in _events(project))
