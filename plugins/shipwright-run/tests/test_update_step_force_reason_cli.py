"""The `update-step` CLI surface for the override-reason rule (FR-01.01).

`update_step()` enforces the rule for library callers (see
test_validation_override_record.py). These probes cover the surface an operator
and a phase SKILL.md actually touch: `--force` without `--force-reason` must be
refused with a readable message rather than a ValueError traceback, and a reason
supplied on the command line must reach the durable record unchanged.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config, load_run_config  # noqa: E402
from orchestrator_pkg.validation_record import VALIDATION_OVERRIDES_KEY  # noqa: E402

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "orchestrator.py")
REASON = "release window closes tonight; missing mockups tracked in #123"


@pytest.fixture
def run_project(tmp_project):
    """A run the `update-step` CLI can actually advance.

    `update-step` is INERT in a driven `mode: single_session` run
    (iterate-2026-07-14-phase-invocation-mode) — `single-session-apply` owns
    completion there and there is no `--force` on that path at all. So the v1
    completion path, and with it this override rule, is only reachable on a
    mode-less v1 / legacy / adopted config. Drop the mode literal to match.
    """
    create_config(
        scope="full_app", profile="supabase-nextjs", autonomy="guided",
        deploy_target="jelastic-dev", project_root=tmp_project,
    )
    path = tmp_project / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    del config["mode"]
    path.write_text(json.dumps(config), encoding="utf-8")
    return tmp_project


def _update_step(project_root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, "update-step", "--project-root", str(project_root),
         "--step", "project", "--status", "complete", *extra],
        capture_output=True, text=True,
    )


def test_force_without_a_reason_is_refused(run_project):
    result = _update_step(run_project, "--force")

    assert result.returncode != 0
    assert "--force-reason" in result.stderr
    config = load_run_config(run_project)
    assert "project" not in config.get("completed_steps", [])
    assert VALIDATION_OVERRIDES_KEY not in config


def test_a_whitespace_only_reason_is_refused_too(run_project):
    """`--force-reason "   "` satisfies argparse but records nothing meaningful."""
    result = _update_step(run_project, "--force", "--force-reason", "   ")

    assert result.returncode != 0
    assert "--force-reason" in result.stderr


def test_a_reason_given_on_the_command_line_reaches_the_record(run_project):
    result = _update_step(run_project, "--force", "--force-reason", REASON)

    assert result.returncode == 0, result.stderr
    record = load_run_config(run_project)[VALIDATION_OVERRIDES_KEY][-1]
    assert record["reason"] == REASON
    assert record["step"] == "project"


def test_completing_without_force_needs_no_reason(run_project):
    """The flag pair is only demanded of an override — an ordinary completion (or
    a pause) is untouched by it."""
    result = _update_step(run_project)

    assert result.returncode == 0, result.stderr
    assert VALIDATION_OVERRIDES_KEY not in load_run_config(run_project)


def test_the_flag_is_advertised_in_help(run_project):
    """An operator hitting the refusal has to be able to find the flag."""
    result = subprocess.run(
        [sys.executable, SCRIPT, "update-step", "--help"],
        capture_output=True, text=True,
    )
    assert "--force-reason" in result.stdout
