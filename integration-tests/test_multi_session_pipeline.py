"""Integration tests for the multi-session run pipeline lifecycle (Plan v4).

These exercise the orchestrator CLI surface end-to-end via subprocess calls,
the same way phase Stop hooks invoke it in production. Unit-level CAS and
state-machine coverage lives in:

    plugins/shipwright-run/tests/test_phase_task_lifecycle.py
    plugins/shipwright-run/tests/test_phase_state_machine.py
    plugins/shipwright-run/tests/test_lifecycle_cli.py

This file's job is the *integration* angle: a real config on disk, a real
chain of subprocess calls, and the assertions that the chain produces a
correct final state.

Scenarios covered:
    1. Happy-path full pipeline: write-config → claim/complete each phase
       → final phase flips run.status to "complete".
    2. Failed phase: complete-phase-task with ok=false routes internally to
       mark-phase-failed, sets run.status=failed, plans no successor.
    3. Direct mark-phase-failed CLI invocation: same end state, exercises
       the explicit failure subcommand surface.
    4. Recovery: recover-phase-task bumps version, releases claim, and the
       original session's complete-phase-task is rejected as stale (exit 2).
    5. Splits freeze: design phase with multi-split design config writes
       splits_frozen and the next phase task is plan/<first split>.
       Empty splits → splitMode=none path.
    6. Schema v1 hard-fail: legacy single-session config is rejected with
       a deterministic exit code (1 = not_found, generic error).

Each test is self-contained and uses a tmp_path scratch project root.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(
    REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py",
)


# ---------- helpers -----------------------------------------------------


def _run_cli(args: list[str], project_root: Path,
             check: bool = True) -> subprocess.CompletedProcess:
    """Invoke orchestrator.py as a subprocess (no AIKIDO env)."""
    env = os.environ.copy()
    env.pop("AIKIDO_CLIENT_ID", None)  # security off → 7-step pipeline
    result = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project_root)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
    )
    if check and result.returncode not in (0, 1, 2):
        raise RuntimeError(
            f"Orchestrator CLI crashed: rc={result.returncode}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
        )
    return result


def _write_config(project_root: Path) -> dict:
    res = _run_cli([
        "write-config",
        "--scope", "full_app",
        "--profile", "supabase-nextjs",
        "--autonomy", "guided",
        "--deploy-target", "jelastic-dev",
    ], project_root)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _read_config(project_root: Path) -> dict:
    return json.loads(
        (project_root / "shipwright_run_config.json").read_text("utf-8"),
    )


def _claim(project_root: Path, *, phase_task_id: str, session_uuid: str,
           expected_phase: str) -> subprocess.CompletedProcess:
    return _run_cli([
        "claim-phase-task",
        "--phase-task-id", phase_task_id,
        "--session-uuid", session_uuid,
        "--expected-phase", expected_phase,
    ], project_root, check=False)


def _complete(project_root: Path, *, phase_task_id: str, session_uuid: str,
              version: int, ok: bool = True,
              extra_result: dict | None = None) -> subprocess.CompletedProcess:
    """Write a result.json next to the config and call complete-phase-task."""
    payload = {"ok": ok}
    if extra_result:
        payload.update(extra_result)
    result_path = project_root / f".result-{phase_task_id}.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    return _run_cli([
        "complete-phase-task",
        "--phase-task-id", phase_task_id,
        "--session-uuid", session_uuid,
        "--version", str(version),
        "--result-json", str(result_path),
    ], project_root, check=False)


def _next_awaiting_launch(config: dict) -> dict | None:
    for task in config.get("phase_tasks", []):
        if task.get("status") == "awaiting_launch":
            return task
    return None


def _walk_phase(project_root: Path, *, expected_phase: str) -> str:
    """Claim + complete the next awaiting_launch task for `expected_phase`.

    Returns the phaseTaskId so callers can chain assertions on it. Asserts
    the next task surfaced really matches expected_phase — guards against
    the state machine drifting on us.
    """
    cfg = _read_config(project_root)
    task = _next_awaiting_launch(cfg)
    assert task is not None, f"no awaiting_launch task; tasks={cfg.get('phase_tasks')}"
    assert task["phase"] == expected_phase, \
        f"expected phase={expected_phase!r}, got {task['phase']!r} (task={task})"

    claim_res = _claim(
        project_root,
        phase_task_id=task["phaseTaskId"],
        session_uuid=task["sessionUuid"],
        expected_phase=expected_phase,
    )
    assert claim_res.returncode == 0, \
        f"claim failed: rc={claim_res.returncode} stdout={claim_res.stdout} stderr={claim_res.stderr}"

    cfg = _read_config(project_root)
    claimed = next(t for t in cfg["phase_tasks"]
                   if t["phaseTaskId"] == task["phaseTaskId"])
    complete_res = _complete(
        project_root,
        phase_task_id=task["phaseTaskId"],
        session_uuid=task["sessionUuid"],
        version=claimed["version"],
        ok=True,
    )
    assert complete_res.returncode == 0, \
        f"complete failed: rc={complete_res.returncode} stdout={complete_res.stdout} stderr={complete_res.stderr}"
    return task["phaseTaskId"]


# ---------- tests -------------------------------------------------------


class TestHappyPathPipeline:
    """Walk the whole pipeline through claim/complete cycles."""

    def test_full_pipeline_completes(self, tmp_path):
        project = tmp_path / "happy-path"
        project.mkdir()

        # Step 1: master writes config (analogue of /shipwright-run Step 4).
        config = _write_config(project)
        assert config["schemaVersion"] == 2
        assert config["status"] == "in_progress"
        assert len(config["phase_tasks"]) == 1
        first = config["phase_tasks"][0]
        assert first["phase"] == "project"
        assert first["status"] == "awaiting_launch"
        assert first["splitId"] is None
        assert first["prerequisites"] == []

        # `pipeline` reflects the actual run environment (security inserted
        # when a scanner is available — semgrep/trivy/gitleaks on PATH or
        # AIKIDO_CLIENT_ID / SHIPWRIGHT_SCANNER_BACKEND set). Walk that exact
        # ordering so the test stays deterministic across hosts.
        expected_phases = list(config["pipeline"])

        # Step 2: walk every phase. Each call simulates a phase Stop hook
        # invoking complete-phase-task (which auto-plans the next phase).
        for phase in expected_phases:
            _walk_phase(project, expected_phase=phase)

        # Step 3: pipeline must be terminal (run-completion invariant).
        final = _read_config(project)
        assert final["status"] == "complete", \
            f"expected complete, got {final['status']!r}; tasks={[t['phase'] + ':' + t['status'] for t in final['phase_tasks']]}"
        for task in final["phase_tasks"]:
            assert task["status"] in ("done", "skipped"), \
                f"non-terminal task at completion: {task}"


class TestFailedPhaseHaltsPipeline:
    """ok=false in result routes to mark-phase-failed; no successor planned."""

    def test_failed_project_halts(self, tmp_path):
        project = tmp_path / "fail-on-project"
        project.mkdir()

        config = _write_config(project)
        first = config["phase_tasks"][0]

        # Claim then complete with ok=false. The subcommand must short-circuit
        # to the mark-phase-failed path and refuse to plan a design task.
        _claim(
            project,
            phase_task_id=first["phaseTaskId"],
            session_uuid=first["sessionUuid"],
            expected_phase="project",
        )
        cfg_after_claim = _read_config(project)
        claimed_version = cfg_after_claim["phase_tasks"][0]["version"]

        res = _complete(
            project,
            phase_task_id=first["phaseTaskId"],
            session_uuid=first["sessionUuid"],
            version=claimed_version,
            ok=False,
            extra_result={"errors": ["missing requirements"]},
        )
        assert res.returncode == 0, res.stderr  # complete-phase-task itself succeeded — failure is data, not exit code

        cfg_after = _read_config(project)
        assert cfg_after["status"] == "failed"
        assert cfg_after["phase_tasks"][0]["status"] == "failed"
        # No design task planned.
        assert all(t["phase"] != "design" for t in cfg_after["phase_tasks"])

    def test_mark_phase_failed_cli_directly(self, tmp_path):
        """Direct mark-phase-failed CLI: same end state as ok=false routing."""
        project = tmp_path / "fail-direct"
        project.mkdir()
        config = _write_config(project)
        first = config["phase_tasks"][0]

        _claim(
            project,
            phase_task_id=first["phaseTaskId"],
            session_uuid=first["sessionUuid"],
            expected_phase="project",
        )
        version = _read_config(project)["phase_tasks"][0]["version"]

        res = _run_cli([
            "mark-phase-failed",
            "--phase-task-id", first["phaseTaskId"],
            "--session-uuid", first["sessionUuid"],
            "--version", str(version),
            "--error", "spec interview crashed",
        ], project, check=False)
        assert res.returncode == 0, f"mark-phase-failed exited non-zero: {res.stderr}"

        cfg_after = _read_config(project)
        assert cfg_after["status"] == "failed"
        assert cfg_after["phase_tasks"][0]["status"] == "failed"
        assert all(t["phase"] != "design" for t in cfg_after["phase_tasks"])


class TestRecoverPhaseTask:
    """recover-phase-task releases the claim and invalidates stale completers."""

    def test_recover_then_stale_complete_rejected(self, tmp_path):
        project = tmp_path / "recover"
        project.mkdir()
        config = _write_config(project)
        first = config["phase_tasks"][0]

        # Crashed session claims the task but never completes.
        _claim(
            project,
            phase_task_id=first["phaseTaskId"],
            session_uuid=first["sessionUuid"],
            expected_phase="project",
        )
        crashed_version = _read_config(project)["phase_tasks"][0]["version"]

        # User runs recover-phase-task. Default --force-status is
        # awaiting_launch; version bumps, claim clears.
        res = _run_cli([
            "recover-phase-task",
            "--phase-task-id", first["phaseTaskId"],
        ], project)
        assert res.returncode == 0, res.stderr

        recovered = _read_config(project)["phase_tasks"][0]
        assert recovered["status"] == "awaiting_launch"
        assert recovered["claimedBySessionUuid"] is None
        assert recovered["version"] > crashed_version

        # The crashed session tries to complete with its now-stale version.
        # Must be rejected with exit 2 (fail-closed).
        stale_res = _complete(
            project,
            phase_task_id=first["phaseTaskId"],
            session_uuid=first["sessionUuid"],
            version=crashed_version,
            ok=True,
        )
        assert stale_res.returncode == 2, \
            f"expected exit 2 for stale complete, got rc={stale_res.returncode}"
        assert "stale" in stale_res.stdout.lower() or "stale" in stale_res.stderr.lower()


class TestFreezeSplitsAtDesignStop:
    """freeze-splits picks up shipwright_design_config.json.splits[]."""

    def test_design_with_three_splits(self, tmp_path):
        project = tmp_path / "splits"
        project.mkdir()
        _write_config(project)

        # Walk project → design as the user would.
        _walk_phase(project, expected_phase="project")

        # Before completing design, write the design config with splits.
        # phase_session_stop.py would write this in production; we shortcut.
        (project / "shipwright_design_config.json").write_text(
            json.dumps({
                "splits": ["01-core", "02-ui-shell", "03-polish"],
            }),
            encoding="utf-8",
        )

        # The Stop hook calls freeze-splits BEFORE complete-phase-task.
        # We simulate that ordering here.
        freeze_res = _run_cli(["freeze-splits"], project)
        assert freeze_res.returncode == 0, freeze_res.stderr

        cfg = _read_config(project)
        assert cfg["splits_frozen"] == ["01-core", "02-ui-shell", "03-polish"]
        assert cfg["runConditions"]["splitMode"] == "per_split"

        # Now complete design — next phase must be plan/01-core.
        design_task = next(
            t for t in cfg["phase_tasks"]
            if t["phase"] == "design" and t["status"] == "awaiting_launch"
        )
        _claim(
            project,
            phase_task_id=design_task["phaseTaskId"],
            session_uuid=design_task["sessionUuid"],
            expected_phase="design",
        )
        claimed_version = next(
            t["version"] for t in _read_config(project)["phase_tasks"]
            if t["phaseTaskId"] == design_task["phaseTaskId"]
        )
        complete_res = _complete(
            project,
            phase_task_id=design_task["phaseTaskId"],
            session_uuid=design_task["sessionUuid"],
            version=claimed_version,
            ok=True,
        )
        assert complete_res.returncode == 0, complete_res.stderr

        cfg_after = _read_config(project)
        plan_tasks = [t for t in cfg_after["phase_tasks"] if t["phase"] == "plan"]
        assert len(plan_tasks) == 1
        assert plan_tasks[0]["splitId"] == "01-core"
        assert plan_tasks[0]["status"] == "awaiting_launch"

    def test_design_with_empty_splits_uses_none_mode(self, tmp_path):
        """splits=[] in design config → splitMode=none, plan has splitId=null."""
        project = tmp_path / "no-splits"
        project.mkdir()
        _write_config(project)
        _walk_phase(project, expected_phase="project")

        (project / "shipwright_design_config.json").write_text(
            json.dumps({"splits": []}),
            encoding="utf-8",
        )
        _run_cli(["freeze-splits"], project)

        cfg = _read_config(project)
        assert cfg["splits_frozen"] == []
        assert cfg["runConditions"]["splitMode"] == "none"

        # Walk through design → plan → expect single null-split plan task.
        _walk_phase(project, expected_phase="design")

        plan_task = next(
            t for t in _read_config(project)["phase_tasks"]
            if t["phase"] == "plan"
        )
        assert plan_task["splitId"] is None


class TestSchemaV1HardFail:
    """v1 configs are rejected by phase-lifecycle subcommands (hard cut)."""

    def test_v1_config_rejected_by_claim(self, tmp_path):
        project = tmp_path / "v1-legacy"
        project.mkdir()
        # Synthesise a legacy single-session config — no schemaVersion field.
        (project / "shipwright_run_config.json").write_text(
            json.dumps({
                "scope": "full_app",
                "profile": "supabase-nextjs",
                "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
                "status": "in_progress",
                "current_step": "project",
                "completed_steps": [],
            }),
            encoding="utf-8",
        )

        res = _run_cli([
            "claim-phase-task",
            "--phase-task-id", "ptk-anything",
            "--session-uuid", "any-uuid",
            "--expected-phase", "project",
        ], project, check=False)
        # v1 hard-fail surfaces as not_found (no phase_tasks[]) which is a
        # generic error, not a fail-closed reason → exit 1 (deterministic).
        # Schema-v1 detection in load_run_config is a future improvement;
        # the user-visible behaviour today is "lifecycle subcommand can't
        # find anything in v1 layout, fails clean".
        assert res.returncode == 1, \
            f"expected exit 1 for v1 not_found, got rc={res.returncode}\n" \
            f"stdout={res.stdout}\nstderr={res.stderr}"
        unchanged = _read_config(project)
        assert "schemaVersion" not in unchanged
        assert "phase_tasks" not in unchanged
