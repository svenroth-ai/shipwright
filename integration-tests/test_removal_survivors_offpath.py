"""INTEGRATION: the survivors that are NOT on the orchestrator loop's happy path.

Third file of the `iterate-2026-07-14-remove-multi-session` `cross_component` coverage,
split out of `test_single_session_sole_mode.py` when that file crossed the 300-LOC limit.
Its siblings:

  * `test_single_session_sole_mode.py` — the loop-driven survivor contract (a full
    7-phase pipeline still runs to `complete` with the engine deleted);
  * `test_multi_session_removal_residue.py` — nothing dangling, nothing over-removed.

What lives HERE is everything the pipeline loop never touches, and which a
loop-only test therefore cannot protect. Each of these broke in a *different* way than
"the pipeline stops working", which is exactly why they need their own file:

  * **gate-policy inertness** — the single most dangerous line in the whole removal.
    `multi_session` was doubling as the "this is not a driven pipeline run" SENTINEL that
    keeps phase gates `interactive`. Delete the literal without replacing the sentinel and
    every standalone/adopted project silently starts AUTO-ANSWERING its gates — with a
    fully green pipeline the whole time. A loop test would never see it.
  * **`generate_handoff_on_stop`** — 95% generic; only its phase-namespaced branch was
    multi-session. Cutting the branch must not take the generic handoff, nor the
    phase-completion fallback, with it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_RESOLVER = REPO_ROOT / "shared" / "scripts" / "tools" / "resolve_gate_policy.py"
HANDOFF_HOOK = REPO_ROOT / "shared" / "scripts" / "hooks" / "generate_handoff_on_stop.py"

CONFIG_NAME = "shipwright_run_config.json"
PIPELINE_PHASES = ("project", "design", "plan", "build", "test", "changelog", "deploy")


# --------------------------------------------------------------------------- #
# Gate policy: THE REGRESSION TRAP of this removal
# --------------------------------------------------------------------------- #

def _resolve_gate(project_root: Path) -> dict:
    res = subprocess.run(
        [sys.executable, str(GATE_RESOLVER),
         "--gate", "project.interview", "--project-root", str(project_root)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_gate_policy_is_inert_for_a_standalone_project(tmp_path):
    """Had the `multi_session` literal simply been deleted with nothing in its place,
    every standalone and adopted project would have started AUTO-ANSWERING its gates —
    including this monorepo, whose own run_config is a v1 standalone with no `mode` key
    at all. The sentinel survives as `gate_policy.INERT_MODE`, and activation stays
    explicit-literal-only.
    """
    project = tmp_path / "standalone"
    project.mkdir()
    (project / CONFIG_NAME).write_text(
        json.dumps({"status": "complete", "standalone": True}), encoding="utf-8",
    )

    payload = _resolve_gate(project)
    assert payload["effective_policy"] == "interactive", (
        "a standalone project must keep INTERACTIVE gates — the removal must not have "
        "auto-armed the gate mechanism everywhere"
    )
    assert payload["should_stop"] is True


def test_gate_policy_activates_for_a_driven_single_session_run(tmp_path):
    """...and it must still ARM for a real run, so the guard is not over-broad."""
    project = tmp_path / "run"
    project.mkdir()
    (project / CONFIG_NAME).write_text(
        json.dumps({"schemaVersion": 2, "mode": "single_session"}), encoding="utf-8",
    )
    assert _resolve_gate(project)["effective_policy"] == "auto-default"


# --------------------------------------------------------------------------- #
# generate_handoff_on_stop: the 95% that was never multi-session
# --------------------------------------------------------------------------- #

def _fire_stop_hook(project: Path) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "SHIPWRIGHT_PROJECT_ROOT": str(project),
           "SHIPWRIGHT_SESSION_ID": "sess-1"}
    return subprocess.run(
        [sys.executable, str(HANDOFF_HOOK)],
        input=json.dumps({"session_id": "sess-1", "cwd": str(project)}),
        capture_output=True, text=True, timeout=120, cwd=str(project), env=env,
    )


def test_generic_handoff_still_written_after_the_phase_branch_was_cut(tmp_path):
    """`generate_handoff_on_stop` lost its phase-namespaced branch (it fired only when the
    live session id matched a `phase_tasks[].sessionUuid` — possible only under the removed
    mode). The other 95% of it — the generic handoff EVERY session writes — must be
    untouched."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / CONFIG_NAME).write_text(
        json.dumps({"schemaVersion": 2, "mode": "single_session", "status": "in_progress",
                    "runId": "run-x", "phase_tasks": []}),
        encoding="utf-8",
    )
    (project / "CLAUDE.md").write_text("# proj\n", encoding="utf-8")

    res = _fire_stop_hook(project)
    assert res.returncode == 0, res.stderr

    handoff = project / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md"
    assert handoff.exists(), (
        "the generic session handoff is no longer written — the phase-branch removal took "
        f"the generic path with it. stderr: {res.stderr}"
    )
    assert handoff.read_text(encoding="utf-8").strip(), "handoff is empty"


def test_phase_completion_fallback_still_fires(tmp_path):
    """The OTHER half of the same hook that had to survive: it detects a phase whose work
    finished but was never marked complete in the run config, and marks it (the standalone
    `/shipwright-project`-without-`/shipwright-run` case).

    Asserting only the handoff FILE would let a regression that silently dropped this
    fallback pass — the hook would still exit 0 and still write its handoff.
    """
    project = tmp_path / "proj"
    project.mkdir()
    (project / "CLAUDE.md").write_text("# proj\n", encoding="utf-8")
    # A v1/standalone run config parked on `project`, whose phase config says complete.
    (project / CONFIG_NAME).write_text(
        json.dumps({"status": "in_progress", "current_step": "project",
                    "completed_steps": [], "standalone": True,
                    "pipeline": list(PIPELINE_PHASES)}),
        encoding="utf-8",
    )
    (project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )

    assert _fire_stop_hook(project).returncode == 0

    cfg = json.loads((project / CONFIG_NAME).read_text(encoding="utf-8"))
    assert "project" in cfg.get("completed_steps", []), (
        "the phase-completion fallback no longer fires — a finished phase would stay "
        f"unmarked in the run config. config: {cfg}"
    )
