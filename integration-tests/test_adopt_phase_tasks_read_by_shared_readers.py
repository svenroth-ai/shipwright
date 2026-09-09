"""Round-trip: the shared phase_tasks[] readers read what adopt actually writes.

`shared/scripts/lib/handoff_pipeline.py` and
`shared/scripts/lib/phase_quality/_engagement.py` both special-case an
adopted-only `phase_tasks[]` array by checking every entry's
`establishedAtAdoption` key — a bare string literal, not a shared constant,
duplicated across the producer (`plugins/shipwright-adopt/scripts/lib/
adopted_phase_tasks.py`) and both consumers. A rename or a shape change on
either side would leave the OTHER green (each side's own unit tests use a
hand-typed literal, never the real producer output) while the fix silently
regresses — exactly the class of bug this file's own diff was written to
close (campaign p4-04-retire-write-once-steps s2, doubt-reviewer finding at
3f-bis).

So this file drives the REAL producer (`write_all`, via subprocess — adopt's
own `lib` namespace would otherwise collide with shared's under this
process's `sys.path`, ADR-045) and feeds its real on-disk output through the
REAL consumers, imported normally here since `integration-tests` is its own
pytest root.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ADOPT_SCRIPTS = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"

sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.handoff_pipeline import render_pipeline_phases  # noqa: E402
from lib.phase_quality._engagement import has_phase_tasks  # noqa: E402


def _adopt_write_all(project_root: Path) -> None:
    """Run adopt's real write_all() in a subprocess, isolated from this
    process's `lib` = shared/scripts/lib binding."""
    script = (
        "import sys; from pathlib import Path;"
        "sys.path.insert(0, r'%s');"
        "from lib.config_writer import write_all;"
        "write_all("
        "  Path(r'%s'), scope='full_app', profile='supabase-nextjs',"
        "  split_name='01-adopted', plugin_version='0.1.0', dev_url=None,"
        "  test_cmd=None, commit_sha=None, features_inferred=1,"
        "  nested_excluded=[], fr_count=1, qr_count=0,"
        ")" % (ADOPT_SCRIPTS, project_root)
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_handoff_pipeline_renders_no_block_for_a_real_adopted_config(tmp_path):
    project = tmp_path / "adopted-repo"
    project.mkdir()
    _adopt_write_all(project)

    run_config = json.loads((project / "shipwright_run_config.json").read_text("utf-8"))
    assert render_pipeline_phases(project, run_config) == [], (
        "a real adopted config's phase_tasks[] rendered a Pipeline Phases block "
        "-- either establishedAtAdoption drifted between adopt's writer and "
        "handoff_pipeline's reader, or the guard regressed"
    )


@pytest.mark.integration
def test_has_phase_tasks_reads_a_real_adopted_config_as_standalone(tmp_path):
    project = tmp_path / "adopted-repo"
    project.mkdir()
    _adopt_write_all(project)

    run_config = json.loads((project / "shipwright_run_config.json").read_text("utf-8"))
    assert has_phase_tasks(run_config) is False, (
        "a real adopted config's phase_tasks[] read as orchestrator-driven "
        "evidence -- either establishedAtAdoption drifted between adopt's "
        "writer and phase_quality's reader, or the guard regressed"
    )
