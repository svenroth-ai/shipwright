"""WP2/F11: update_step persists against a FRESH reload under the lock.

The slow compliance subprocess runs OUTSIDE the lock; a concurrent writer
landing a change during that window must NOT be clobbered when update_step
finally writes back. This is the deterministic counterpart to the
two-process storm in test_runconfig_concurrency.py.
"""
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from orchestrator import (  # noqa: E402
    create_config,
    load_run_config,
    save_run_config,
    update_step,
)


def test_update_step_complete_does_not_clobber_concurrent_write(tmp_path, mocker):
    """Simulate another writer mutating the on-disk config during the
    (unlocked) compliance window. update_step must reload fresh inside the
    lock and preserve that mutation alongside its own (audit WP2/F11)."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_path)

    def _concurrent_writer(project_root, phase):
        # Mimics phase_task_lifecycle / append_phase_history landing a write
        # to a field update_step does not own, mid-compliance.
        cfg = load_run_config(project_root)
        cfg.setdefault("phase_history", {})["__concurrent__"] = [{"run_id": "other"}]
        save_run_config(project_root, cfg)
        return {"updated_reports": []}

    mocker.patch("orchestrator.run_compliance_update", side_effect=_concurrent_writer)

    config = update_step(tmp_path, "project", "complete", force=True)

    # update_step's own field landed ...
    assert "project" in config["completed_steps"]

    # ... AND the concurrent writer's field survived on disk (the pre-fix code
    # saved a stale in-memory copy and clobbered it).
    persisted = load_run_config(tmp_path)
    assert persisted["phase_history"]["__concurrent__"] == [{"run_id": "other"}]
    assert "project" in persisted["completed_steps"]


def test_update_step_in_progress_preserves_unrelated_fields(tmp_path):
    """The in_progress quick-RMW path reloads fresh too: a field written
    between create and update_step is not lost."""
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_path)
    cfg = load_run_config(tmp_path)
    cfg["phase_tasks"] = [{"phaseTaskId": "ptk-x", "phase": "build", "version": 3}]
    save_run_config(tmp_path, cfg)

    update_step(tmp_path, "build", "in_progress")

    persisted = load_run_config(tmp_path)
    assert persisted["current_step"] == "build"
    assert persisted["phase_tasks"] == [{"phaseTaskId": "ptk-x", "phase": "build", "version": 3}]
