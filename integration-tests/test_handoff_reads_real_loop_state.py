"""Round-trip: the handoff renderer reads what the orchestrator actually writes.

`shared/scripts/lib/handoff_pipeline.py` is a pure CONSUMER of two JSON contracts
owned by `plugins/shipwright-run` — `shipwright_run_config.json` → `phase_tasks[]`
and `.shipwright/run_loop_state.json`. `shared/` must not import from a plugin, so
the consumer keeps its own copy of the loop-state path.

That duplication is the risk this file exists for. Because a missing or unreadable
loop state degrades *silently* (by design — the file does not exist before the
first dispatch), a rename on the producer side would make the handoff quietly stop
showing the dispatch pointer with every unit test still green. External plan review
flagged exactly this (finding G3).

So the tests below use no hand-written fixture. They drive the real orchestrator
CLI, let it write both files, and assert the renderer reads them — plus a direct
drift-guard on the path constant itself.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LIB = REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
ORCHESTRATOR = str(RUN_LIB / "orchestrator.py")

sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.handoff_pipeline import LOOP_STATE_REL_PATH, render_pipeline_phases  # noqa: E402


def _run_cli(args: list[str], project_root: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("AIKIDO_CLIENT_ID", None)
    return subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project_root)],
        capture_output=True, text=True, encoding="utf-8", timeout=60, env=env,
    )


@pytest.fixture
def dispatched_run(tmp_path):
    """A real single-session run with one phase claimed and dispatched.

    Both artefacts the renderer reads are produced by their real owners:
    `phase_tasks[]` by `create_config` + `phase_task_lifecycle.claim_phase_task`,
    and `run_loop_state.json` by `single_session/loop_state.save_loop_state`.
    """
    project = tmp_path / "handoff-roundtrip"
    project.mkdir()

    res = _run_cli([
        "write-config", "--scope", "full_app", "--profile", "supabase-nextjs",
        "--autonomy", "guided", "--mode", "single_session",
    ], project)
    assert res.returncode == 0, res.stderr

    res = _run_cli(["single-session-next"], project)
    assert res.returncode == 0, res.stderr
    dispatch = json.loads(res.stdout)["dispatch"]
    return project, dispatch


# --------------------------------------------------------------------------- #
# The path constant itself
# --------------------------------------------------------------------------- #

@pytest.mark.integration
def test_the_consumer_and_the_producer_agree_on_the_loop_state_path():
    """Read the owner's constant out of the owning module, in a subprocess so the
    plugin's `lib` namespace never pollutes this session (ADR-044)."""
    probe = (
        "import sys; sys.path.insert(0, r'%s');"
        "from single_session.loop_state import LOOP_STATE_REL_PATH;"
        "print(LOOP_STATE_REL_PATH.as_posix())" % RUN_LIB
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    owner_path = result.stdout.strip()

    assert owner_path == LOOP_STATE_REL_PATH, (
        f"handoff_pipeline.LOOP_STATE_REL_PATH is {LOOP_STATE_REL_PATH!r} but the "
        f"owning module now writes {owner_path!r}. The handoff would silently stop "
        "showing the dispatch pointer — update the shared copy."
    )


# --------------------------------------------------------------------------- #
# The real files, read by the real renderer
# --------------------------------------------------------------------------- #

@pytest.mark.integration
def test_the_renderer_reads_the_loop_state_the_orchestrator_wrote(dispatched_run):
    project, dispatch = dispatched_run
    assert (project / LOOP_STATE_REL_PATH).is_file(), (
        "the orchestrator did not write loop state where the renderer looks"
    )

    config = json.loads((project / "shipwright_run_config.json").read_text("utf-8"))
    out = "\n".join(render_pipeline_phases(project, config))

    # The claimed phase is named as dispatched, and NOT counted as finished.
    assert f"- **Currently dispatched**: `{dispatch['phase']}`" in out
    assert "- **Loop status**: running" in out
    assert "- **Finished**: 0 of" in out
    assert f"| {dispatch['phase']} | — | in_progress | **no — interrupted** |" in out


@pytest.mark.integration
def test_a_phase_the_orchestrator_completed_is_reported_as_finished(dispatched_run):
    """Complete the dispatched phase through the real apply path, then re-render:
    the status the lifecycle wrote must move the row from interrupted to finished."""
    project, dispatch = dispatched_run

    artifact = project / "artifacts" / f"{dispatch['phase']}.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(f"# {dispatch['phase']}\n", encoding="utf-8")
    result_path = project / "result.json"
    result_path.write_text(json.dumps({
        "ok": True, "phase": dispatch["phase"], "summary": "done",
        "artifacts": [f"artifacts/{dispatch['phase']}.md"],
    }), encoding="utf-8")

    res = _run_cli([
        "single-session-apply",
        "--phase-task-id", dispatch["phaseTaskId"],
        "--session-uuid", dispatch["sessionUuid"],
        "--version", str(dispatch["version"]),
        "--result-json", str(result_path),
    ], project)
    assert res.returncode == 0, res.stderr

    config = json.loads((project / "shipwright_run_config.json").read_text("utf-8"))
    out = "\n".join(render_pipeline_phases(project, config))

    assert f"| {dispatch['phase']} | — | done | yes |" in out
    assert "- **Interrupted**: none — no phase is mid-flight" in out
    assert "- **Finished**: 1 of" in out
