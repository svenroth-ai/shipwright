"""Integration test: single-session orchestrator loop end-to-end (SS3).

The single_session master drives the whole pipeline in ONE conversation by
alternating two CLI subcommands — ``single-session-next`` (resolve + claim +
record) and ``single-session-apply`` (contract-validate + complete + advance) —
with a phase-runner subagent in between. Here the *test* plays the phase-runner:
after each ``next`` it constructs a phase-runner RESULT CONTRACT payload and
feeds it to ``apply``, exactly as the master would with the subagent's return.

This is the composition proof for SS3 (AC1/AC3/AC4): a real config on disk, a
real chain of orchestrator subprocess calls (the same surface the master
invokes), the SAME ``phase_task_lifecycle`` helpers the multi_session Stop hook
uses — no bespoke completion path.

Scenarios:
    1. Full pipeline incl. build fan-out (2 splits) advances to complete, and the
       serial split order (plan/01 -> build/01 -> plan/02 -> build/02) is preserved.
    2. Forced phase failure strict-stops via mark_phase_failed: run.status=failed,
       NO successor planned, loop_state stamped failed.

Unit-level coverage of resolve/claim/apply lives in
``plugins/shipwright-run/tests/test_single_session_loop.py``.
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


# ---------- helpers -----------------------------------------------------

def _run_cli(args: list[str], project_root: Path,
             check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AIKIDO_CLIENT_ID", None)
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


def _write_ss_config(project: Path) -> dict:
    # NB: --mode single_session is what makes the loop subcommands live.
    res = _run_cli([
        "write-config", "--scope", "full_app", "--profile", "supabase-nextjs",
        "--autonomy", "guided", "--mode", "single_session",
    ], project)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _read_config(project: Path) -> dict:
    return json.loads((project / "shipwright_run_config.json").read_text("utf-8"))


def _read_loop_state(project: Path) -> dict:
    return json.loads((project / ".shipwright" / "run_loop_state.json").read_text("utf-8"))


def _next(project: Path) -> dict:
    res = _run_cli(["single-session-next"], project, check=False)
    return json.loads(res.stdout)


def _apply(project: Path, dispatch: dict, *, ok: bool = True) -> dict:
    """Play the phase-runner: persist artifacts to disk + build a RESULT CONTRACT
    payload + call apply. A real phase-runner writes its outputs to disk BEFORE
    returning, so we do too — the SS4 on-disk persistence guard verifies it."""
    phase = dispatch["phase"]
    artifact_rel = f"artifacts/{phase}.md"
    payload = {
        "ok": ok,
        "phase": phase,
        "summary": f"{phase} completed" if ok else f"{phase} failed",
        "artifacts": [artifact_rel],
    }
    if dispatch.get("splitId"):
        payload["splitId"] = dispatch["splitId"]
    if not ok:
        payload["reason"] = f"{phase} blew up in the runner"

    if ok:  # persist the claimed artifact so the loop's SS4 guard passes
        art = project / artifact_rel
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(f"# {phase}\n", encoding="utf-8")

    result_path = project / f".result-{dispatch['phaseTaskId']}.json"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    res = _run_cli([
        "single-session-apply",
        "--phase-task-id", dispatch["phaseTaskId"],
        "--session-uuid", dispatch["sessionUuid"],
        "--version", str(dispatch["version"]),
        "--result-json", str(result_path),
    ], project, check=False)
    assert res.returncode in (0, 1, 2), res.stderr
    return json.loads(res.stdout)


def _drive(project: Path, expected_phase: str, *, expected_split: str | None = None,
           ok: bool = True, design_splits: list[str] | None = None) -> tuple[dict, dict]:
    nxt = _next(project)
    assert nxt["action"] == "dispatch", f"expected dispatch, got {nxt}"
    dispatch = nxt["dispatch"]
    assert dispatch["phase"] == expected_phase, dispatch
    assert dispatch["splitId"] == expected_split, dispatch

    if expected_phase == "design" and design_splits is not None:
        (project / "shipwright_design_config.json").write_text(
            json.dumps({"splits": design_splits}), encoding="utf-8",
        )
    applied = _apply(project, dispatch, ok=ok)
    return dispatch, applied


# ---------- tests -------------------------------------------------------

class TestFullPipelineSingleSession:
    """project -> ... -> deploy in ONE loop, incl. serial build fan-out."""

    def test_full_pipeline_with_split_fanout_completes(self, tmp_path):
        project = tmp_path / "ss-happy"
        project.mkdir()
        config = _write_ss_config(project)
        assert config["mode"] == "single_session"
        assert config["status"] == "in_progress"

        order: list[tuple[str, str | None]] = []

        _drive(project, "project")
        order.append(("project", None))
        _drive(project, "design", design_splits=["01-core", "02-ui"])
        order.append(("design", None))

        # Serial split fan-out: plan/01 -> build/01 -> plan/02 -> build/02.
        for split in ("01-core", "02-ui"):
            _drive(project, "plan", expected_split=split)
            order.append(("plan", split))
            _drive(project, "build", expected_split=split)
            order.append(("build", split))

        for phase in ("test", "changelog", "deploy"):
            _drive(project, phase)
            order.append((phase, None))

        assert order == [
            ("project", None), ("design", None),
            ("plan", "01-core"), ("build", "01-core"),
            ("plan", "02-ui"), ("build", "02-ui"),
            ("test", None), ("changelog", None), ("deploy", None),
        ], "serial split order not preserved"

        # Pipeline terminal — run-completion invariant + loop terminal.
        final = _read_config(project)
        assert final["status"] == "complete", [
            t["phase"] + ":" + t["status"] for t in final["phase_tasks"]
        ]
        assert all(t["status"] in ("done", "skipped") for t in final["phase_tasks"])

        terminal = _next(project)
        assert terminal["action"] == "complete"
        assert _read_loop_state(project)["status"] == "complete"


class TestForcedFailureStrictStop:
    """ok=false routes to mark_phase_failed; no successor; loop stamped failed."""

    def test_failure_mid_pipeline_halts_with_no_successor(self, tmp_path):
        project = tmp_path / "ss-fail"
        project.mkdir()
        _write_ss_config(project)

        _drive(project, "project")
        _drive(project, "design", design_splits=[])  # empty splits -> single pass
        _dispatch, applied = _drive(project, "plan", ok=False)

        assert applied["ok"] is True  # complete-phase-task itself succeeded
        assert applied["run_status"] == "failed"

        cfg = _read_config(project)
        assert cfg["status"] == "failed"
        assert all(t["phase"] != "build" for t in cfg["phase_tasks"]), "no successor"

        terminal = _next(project)
        assert terminal["action"] == "failed"
        assert terminal["failed_tasks"] and terminal["failed_tasks"][0]["phase"] == "plan"
        assert _read_loop_state(project)["status"] == "failed"


class TestPersistenceGuardCrossComponent:
    """SS4 (cross_component integration coverage): the phase-runner artifact
    contract, ``phase_task_lifecycle``, and the on-disk PERSISTENCE GUARD compose
    across the real subprocess CLI surface — an ``ok`` result that CLAIMS an
    artifact it never wrote to disk is rejected fail-closed, leaving the frontier
    intact for a retry (no silent loss, no bespoke completion path)."""

    def test_claimed_but_unwritten_artifact_is_rejected(self, tmp_path):
        project = tmp_path / "ss-guard"
        project.mkdir()
        _write_ss_config(project)

        nxt = _next(project)
        assert nxt["action"] == "dispatch"
        dispatch = nxt["dispatch"]

        # ok result claims artifacts/project.md but NOTHING was written to disk.
        payload = {
            "ok": True, "phase": "project", "summary": "project completed",
            "artifacts": ["artifacts/project.md"],
        }
        result_path = project / ".result-missing.json"
        result_path.write_text(json.dumps(payload), encoding="utf-8")
        res = _run_cli([
            "single-session-apply",
            "--phase-task-id", dispatch["phaseTaskId"],
            "--session-uuid", dispatch["sessionUuid"],
            "--version", str(dispatch["version"]),
            "--result-json", str(result_path),
        ], project, check=False)

        assert res.returncode == 1, res.stderr  # guard reject (not a fail-closed CAS)
        out = json.loads(res.stdout)
        assert out["ok"] is False
        assert out["reason"] == "artifacts_missing"
        assert out["missing"] == ["artifacts/project.md"]

        # Fail-closed: the task was NOT completed — run still in_progress, and the
        # frontier still points at project (idempotent re-dispatch after a fix).
        assert _read_config(project)["status"] == "in_progress"
        again = _next(project)
        assert again["action"] == "dispatch"
        assert again["dispatch"]["phase"] == "project"
