"""Capstone integration test: the single-session pipeline, end to end (SS7).

The safety net the whole ``2026-07-07-single-session-pipeline`` campaign builds
toward. Where SS3 proved the happy fan-out and strict-stop and SS5 proved
kill-and-resume, this capstone proves what no existing integration test does:

  * **(A) a full pipeline walked THROUGH a human gate + strict-stop mid-fan-out.**
    project -> design -> plan/build fan-out -> test -> changelog -> deploy, over the
    real orchestrator subprocess CLI (the surface the master invokes), pausing at
    the deploy gate (``single-session-gate``) and resuming — with the SS4
    **section-writer** persistence regression threaded into the plan phase (a
    claimed-but-unwritten artifact is rejected mid-pipeline, the frontier survives,
    the fixed retry completes).

  * **(B) cross-surface parity.** The loop is surface-AGNOSTIC: the same pipeline
    driven under ``CLAUDE_CODE_ENTRYPOINT=cli`` vs ``claude-vscode`` yields the
    IDENTICAL — and correct — dispatch sequence + terminal state. That is *why* CLI
    and WebUI reach parity: both drive this one CLI, which reads no surface env.

The chat surface's honest decline + multi-session back-compat + the external_review
roster pin live in ``test_cross_surface_backcompat.py``. The real WebUI browser
flow (Playwright) is campaign sub-iterate **SS8** (repo ``shipwright-webui``,
prereq S1b) — it cannot run in this monorepo.
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

def _run_cli(args: list[str], project_root: Path, *,
             env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    res = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project_root)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
    )
    if res.returncode not in (0, 1, 2):
        raise RuntimeError(
            f"Orchestrator CLI crashed: rc={res.returncode}\n"
            f"stdout={res.stdout!r}\nstderr={res.stderr!r}",
        )
    return res


def _write_ss_config(project: Path, *, env_extra: dict | None = None) -> dict:
    res = _run_cli([
        "write-config", "--scope", "full_app", "--profile", "supabase-nextjs",
        "--autonomy", "guided", "--mode", "single_session",
    ], project, env_extra=env_extra)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _read_config(project: Path) -> dict:
    return json.loads((project / "shipwright_run_config.json").read_text("utf-8"))


def _read_loop_state(project: Path) -> dict:
    return json.loads((project / ".shipwright" / "run_loop_state.json").read_text("utf-8"))


def _events(project: Path) -> list[str]:
    path = project / ".shipwright" / "run_loop_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln)["event"] for ln in path.read_text("utf-8").splitlines() if ln.strip()]


def _next(project: Path, *, env_extra: dict | None = None) -> dict:
    return json.loads(_run_cli(["single-session-next"], project, env_extra=env_extra).stdout)


def _apply(project: Path, dispatch: dict, *, ok: bool = True, persist: bool = True,
           env_extra: dict | None = None) -> tuple[int, dict]:
    """Play the phase-runner: (optionally) persist the claimed artifact to disk,
    then call apply. ``persist=False`` models the section-writer bug — an ok result
    that CLAIMS an artifact it never wrote."""
    phase = dispatch["phase"]
    artifact_rel = f"artifacts/{phase}{'-' + dispatch['splitId'] if dispatch.get('splitId') else ''}.md"
    payload = {"ok": ok, "phase": phase, "artifacts": [artifact_rel],
               "summary": f"{phase} {'done' if ok else 'failed'}"}
    if dispatch.get("splitId"):
        payload["splitId"] = dispatch["splitId"]
    if not ok:
        payload["reason"] = f"{phase} failed in the runner"
    if ok and persist:
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
    ], project, env_extra=env_extra)
    return res.returncode, json.loads(res.stdout)


def _drive(project: Path, expected_phase: str, *, expected_split: str | None = None,
           design_splits: list[str] | None = None,
           env_extra: dict | None = None) -> dict:
    """next -> (design config) -> apply, asserting the frontier matches."""
    nxt = _next(project, env_extra=env_extra)
    assert nxt["action"] == "dispatch", nxt
    dispatch = nxt["dispatch"]
    assert dispatch["phase"] == expected_phase and dispatch["splitId"] == expected_split, dispatch
    if expected_phase == "design" and design_splits is not None:
        (project / "shipwright_design_config.json").write_text(
            json.dumps({"splits": design_splits}), encoding="utf-8",
        )
    rc, applied = _apply(project, dispatch, env_extra=env_extra)
    assert rc == 0 and applied["ok"] is True, applied
    return dispatch


# ---------- (A) gate-walk + section-writer regression ------------------

class TestFullPipelineThroughHumanGate:
    """Full single-session pipeline advances to complete THROUGH a deploy human
    gate, with the section-writer persistence guard proven mid-pipeline."""

    def test_gate_walk_with_section_writer_regression(self, tmp_path):
        project = tmp_path / "ss-capstone"
        project.mkdir()
        assert _write_ss_config(project)["mode"] == "single_session"

        _drive(project, "project")
        _drive(project, "design", design_splits=["01-core", "02-ui"])

        # --- plan/01: section-writer regression THREADED into the live pipeline ---
        nxt = _next(project)
        plan01 = nxt["dispatch"]
        assert (plan01["phase"], plan01["splitId"]) == ("plan", "01-core"), plan01
        # ok result CLAIMS artifacts/plan-01-core.md but writes nothing -> rejected.
        rc, rej = _apply(project, plan01, persist=False)
        assert rc == 1 and rej["ok"] is False, rej
        assert rej["reason"] == "artifacts_missing"
        assert rej["missing"] == ["artifacts/plan-01-core.md"]
        # Fail-closed: frontier intact, run still in_progress -> the fixed retry lands.
        assert _read_config(project)["status"] == "in_progress"
        rc, ok = _apply(project, plan01, persist=True)  # same descriptor, version unbumped
        assert rc == 0 and ok["ok"] is True, ok

        _drive(project, "build", expected_split="01-core")
        _drive(project, "plan", expected_split="02-ui")
        _drive(project, "build", expected_split="02-ui")
        _drive(project, "test")
        _drive(project, "changelog")

        # --- deploy: pause at the human gate, resume, then apply ---
        deploy = _next(project)["dispatch"]
        assert deploy["phase"] == "deploy", deploy
        paused = _run_cli([
            "single-session-gate", "--phase-task-id", deploy["phaseTaskId"],
            "--phase", "deploy", "--state", "pause",
        ], project)
        assert json.loads(paused.stdout)["status"] == "paused_human_gate"
        assert _read_loop_state(project)["status"] == "paused_human_gate"
        resumed = _run_cli([
            "single-session-gate", "--phase-task-id", deploy["phaseTaskId"],
            "--phase", "deploy", "--state", "resume",
        ], project)
        assert json.loads(resumed.stdout)["status"] == "running"
        rc, applied = _apply(project, deploy)
        assert rc == 0 and applied["ok"] is True

        # Pipeline + loop are terminal.
        assert _read_config(project)["status"] == "complete"
        assert _next(project)["action"] == "complete"
        assert _read_loop_state(project)["status"] == "complete"

        # The observability log carries the whole story, gate included.
        seq = _events(project)
        assert seq.count("human_gate_pause") == 1 and seq.count("human_gate_resume") == 1
        # pause/resume sit between the deploy dispatch and its phase_result, in order.
        assert seq[-4:] == ["dispatch", "human_gate_pause", "human_gate_resume", "phase_result"]
        # No strict_stop on a clean run; every phase produced exactly one result.
        assert "strict_stop" not in seq
        assert seq.count("phase_result") == 9  # project,design,plan01,build01,plan02,build02,test,changelog,deploy


# ---------- (A') strict-stop mid-fan-out -------------------------------

class TestStrictStopMidFanout:
    """A failure DURING the serial split fan-out halts the run and plans NO
    successor split — the harder companion to SS3's fail-at-plan strict-stop
    (which has no fan-out). Successors are planned incrementally, so split 02-ui
    must never become a task once build/01-core fails."""

    def test_build_failure_mid_fanout_halts_and_plans_no_next_split(self, tmp_path):
        project = tmp_path / "ss-strictstop"
        project.mkdir()
        _write_ss_config(project)

        _drive(project, "project")
        _drive(project, "design", design_splits=["01-core", "02-ui"])
        _drive(project, "plan", expected_split="01-core")

        build01 = _next(project)["dispatch"]
        assert (build01["phase"], build01["splitId"]) == ("build", "01-core"), build01
        rc, applied = _apply(project, build01, ok=False)
        assert applied["ok"] is True and applied["run_status"] == "failed", applied

        cfg = _read_config(project)
        assert cfg["status"] == "failed"
        assert not any(t.get("splitId") == "02-ui" for t in cfg["phase_tasks"]), \
            "strict-stop must NOT plan the next split"
        assert _read_loop_state(project)["status"] == "failed"

        terminal = _next(project)
        assert terminal["action"] == "failed"
        assert terminal["failed_tasks"][0]["phase"] == "build"

        seq = _events(project)
        assert seq[-1] == "strict_stop", seq
        assert seq.count("strict_stop") == 1


# ---------- (B) cross-surface parity -----------------------------------

# The one correct pipeline both surfaces must produce (splits=["01-core"]).
_EXPECTED_PIPELINE = [
    ("project", None), ("design", None), ("plan", "01-core"), ("build", "01-core"),
    ("test", None), ("changelog", None), ("deploy", None),
]


def _drive_happy_pipeline(project: Path, env_extra: dict) -> tuple[list[tuple], str]:
    """Drive a clean pipeline under a given surface env; return (dispatch order,
    terminal status). Each step is asserted to be the CORRECT frontier — so the
    sequence is verified right, not merely equal to the other surface's."""
    order: list[tuple] = []

    def rec(phase: str, split: str | None = None, design_splits=None):
        nxt = _next(project, env_extra=env_extra)
        assert nxt["action"] == "dispatch", nxt
        d = nxt["dispatch"]
        assert (d["phase"], d["splitId"]) == (phase, split), d  # correct frontier, per surface
        order.append((d["phase"], d["splitId"]))
        if phase == "design" and design_splits is not None:
            (project / "shipwright_design_config.json").write_text(
                json.dumps({"splits": design_splits}), encoding="utf-8")
        rc, applied = _apply(project, d, env_extra=env_extra)
        assert rc == 0 and applied["ok"] is True, applied

    rec("project")
    rec("design", design_splits=["01-core"])
    rec("plan", "01-core")
    rec("build", "01-core")
    for ph in ("test", "changelog", "deploy"):
        rec(ph)
    return order, _read_config(project)["status"]


# The three real surfaces: plain CLI, the WebUI (embedded terminal + its marker),
# and chat (VS Code / desktop). SHIPWRIGHT_WEBUI is the aspirational WebUI marker —
# driving it makes this guard BITE if the loop ever grows a surface branch, not
# merely assert an invariance that holds only because the env is unread today.
_SURFACES = {
    "cli": {"CLAUDE_CODE_ENTRYPOINT": "cli"},
    "webui": {"CLAUDE_CODE_ENTRYPOINT": "cli", "SHIPWRIGHT_WEBUI": "1"},
    "chat": {"CLAUDE_CODE_ENTRYPOINT": "claude-vscode"},
}


class TestCrossSurfaceParity:
    """CLI, WebUI, and chat all drive this one CLI, which reads no surface env — so
    each gets an IDENTICAL and CORRECT pipeline. Chat's honest decline (it can't
    launch a bound multi_session session) is asserted in
    test_cross_surface_backcompat.py."""

    def test_pipeline_identical_across_surfaces(self, tmp_path):
        seen: dict[str, tuple] = {}
        for name, env in _SURFACES.items():
            proj = tmp_path / name
            proj.mkdir()
            _write_ss_config(proj, env_extra=env)
            order, status = _drive_happy_pipeline(proj, env)
            # Each surface produced the CORRECT sequence (not just mutually equal).
            assert order == _EXPECTED_PIPELINE and status == "complete", (name, order, status)
            seen[name] = (tuple(order), tuple(_events(proj)))
        # Surface — including the SHIPWRIGHT_WEBUI marker — leaks nowhere: one story.
        assert len(set(seen.values())) == 1, seen
