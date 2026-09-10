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

Sub-iterate s2b extends this file with the BACKFILL producer
(`scripts/tools/backfill_phase_tasks.py`), driven the same subprocess way,
against a config shaped like a repo adopted BEFORE s2 — completed_steps +
adoption, no phase_tasks[] at all — so the same two shared readers are
proven to see the backfilled entries exactly as they see s2's write-time
ones.
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


def _write_pre_s2_adopted_config(project_root: Path) -> None:
    """A config shaped exactly like a real repo adopted before s2 landed:
    completed_steps + adoption present, phase_tasks[] absent entirely."""
    project_root.mkdir(parents=True, exist_ok=True)
    config = {
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "status": "complete",
        "current_step": None,
        "completed_steps": ["project", "plan", "build", "test"],
        "standalone": False,
        "adoption": {
            "adopted_at": "2026-05-29T07:52:55.356956+00:00",
            "commit_at_adoption": "c5deef120d3fee88e42be4bd9de5e6b0610d2ba1",
            "features_inferred": 0,
            "nested_excluded": [],
            "plugin_version": "0.1.0",
        },
        "updated_at": "2026-05-29T07:52:55.356956+00:00",
    }
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8",
    )


def _run_backfill(project_root: Path) -> None:
    """Run the real backfill tool in a subprocess, same isolation rationale
    as `_adopt_write_all`."""
    script = (
        "import sys; from pathlib import Path;"
        "sys.path.insert(0, r'%s');"
        "from tools.backfill_phase_tasks import run;"
        "run(Path(r'%s'), dry_run=False)"
        % (ADOPT_SCRIPTS, project_root)
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


@pytest.mark.integration
def test_handoff_pipeline_renders_no_block_for_a_backfilled_pre_s2_config(tmp_path):
    """Same guard as the fresh-adoption test above, driven through the
    BACKFILL producer instead of write_all -- a repo adopted before s2
    (completed_steps + adoption, no phase_tasks[] at all) must round-trip
    through the real backfill tool and still read the same way."""
    project = tmp_path / "pre-s2-adopted-repo"
    _write_pre_s2_adopted_config(project)
    _run_backfill(project)

    run_config = json.loads((project / "shipwright_run_config.json").read_text("utf-8"))
    assert run_config["phase_tasks"], "the backfill produced no phase_tasks[] entries"
    assert render_pipeline_phases(project, run_config) == [], (
        "a backfilled pre-s2 adopted config's phase_tasks[] rendered a "
        "Pipeline Phases block -- the establishedAtAdoption guard regressed "
        "for the backfill path specifically"
    )


@pytest.mark.integration
def test_has_phase_tasks_reads_a_backfilled_pre_s2_config_as_standalone(tmp_path):
    project = tmp_path / "pre-s2-adopted-repo"
    _write_pre_s2_adopted_config(project)
    _run_backfill(project)

    run_config = json.loads((project / "shipwright_run_config.json").read_text("utf-8"))
    assert has_phase_tasks(run_config) is False, (
        "a backfilled pre-s2 adopted config's phase_tasks[] read as "
        "orchestrator-driven evidence -- the establishedAtAdoption guard "
        "regressed for the backfill path specifically"
    )
