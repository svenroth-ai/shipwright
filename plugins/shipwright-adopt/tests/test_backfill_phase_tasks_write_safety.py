"""Write-safety tests for ``scripts/tools/backfill_phase_tasks.py``, split out
of ``test_backfill_phase_tasks_cli.py`` (bloat gate).

Doubt-reviewer, s2b: the read-modify-write must be held under the same
advisory lock every other run-config writer honours -- a bare read-then-write
would let this tool's full-document write clobber whatever a live
``/shipwright-run`` session committed in between (the tool's own stated
trigger scenario: a repo "later picked up by ``/shipwright-run`` for a new
feature"). PR-review gate, s2b PR #701: a present-but-non-string
``adoption.adopted_at`` must never propagate into a generated task record.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import tools.backfill_phase_tasks as backfill_cli
from tools.backfill_phase_tasks import RUN_CONFIG_NAME, run
from file_lock import file_lock

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "backfill_phase_tasks"


def _copy_config(src_name: str, project_root: Path) -> Path:
    project_root.mkdir(parents=True, exist_ok=True)
    dest = project_root / RUN_CONFIG_NAME
    shutil.copyfile(_FIXTURES / src_name, dest)
    return dest


def test_a_held_lock_blocks_the_backfill_instead_of_racing_it(
    tmp_path: Path, monkeypatch
) -> None:
    """Simulates a concurrent orchestrator session already holding the
    run-config lock. Proves two things at once: the CLI actually contends
    for the SAME lock-file path a real writer would hold (not a no-op), and
    a lock it cannot acquire fails loudly (SystemExit) rather than racing
    past it and clobbering whatever the other holder is writing."""
    monkeypatch.setattr(backfill_cli, "LOCK_TIMEOUT_SECONDS", 0.2)
    project = tmp_path / "leadwright"
    config_path = _copy_config("leadwright_run_config.json", project)
    lock_path = project / (RUN_CONFIG_NAME + backfill_cli.LOCK_SUFFIX)

    with file_lock(lock_path, timeout_seconds=5.0):
        with pytest.raises(SystemExit, match="could not acquire the run-config lock"):
            run(project, dry_run=False)

    # The lock is released again once the simulated holder's `with` exits --
    # a normal run now succeeds, proving the failure above was contention,
    # not a broken lock path.
    result = run(project, dry_run=False)
    assert result["written"] is True
    assert "phase_tasks" in json.loads(config_path.read_text(encoding="utf-8"))


def test_a_non_string_adopted_at_falls_back_to_now_instead_of_propagating(
    tmp_path: Path,
) -> None:
    """PR-review comment, s2b PR #701: adoption.adopted_at is human-editable
    JSON and could carry anything (a number, a nested object). Schema
    PhaseTask.createdAt is format:date-time -- a non-string value must never
    reach a generated task record verbatim."""
    project = tmp_path / "malformed-timestamp"
    project.mkdir()
    (project / RUN_CONFIG_NAME).write_text(
        json.dumps(
            {
                "completed_steps": ["project"],
                "adoption": {"adopted_at": 12345},
            }
        ),
        encoding="utf-8",
    )

    result = run(project, dry_run=False)

    after = json.loads((project / RUN_CONFIG_NAME).read_text(encoding="utf-8"))
    assert result["written"] is True
    created_at = after["phase_tasks"][0]["createdAt"]
    assert isinstance(created_at, str) and created_at != "12345"
