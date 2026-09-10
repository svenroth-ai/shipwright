"""Regression: standalone->driven merge must not drop a PRE-s5 legacy
config's history (campaign p4-04-retire-write-once-steps, sub-iterate s5).

Before this sub-iterate, the v1 ``update_step`` path wrote progress to
``current_step``/``completed_steps`` only -- it never touched
``phase_tasks[]`` for a standalone run. Any such config already sitting on
disk when s5 lands has ``completed_steps`` but NO ``phase_tasks[]`` at all.
``config_factory.create_config``'s standalone->driven merge reads
``phase_tasks_progress(existing)`` exclusively now that the v1 fields are
retired -- external plan review (GLM + OpenAI, independently, both HIGH)
flagged that a config in exactly this shape would silently lose its
completed-phase history on merge. Confirmed by direct probe before the fix
landed; this test pins the fix: the merge reads ``completed_steps`` as a
ONE-TIME fallback at this boundary alone, never as an ongoing reader path
(mirrors ``adopted_phase_tasks.backfill_missing_phase_tasks``'s identical
one-time-migration shape on the adopt side).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402

from lib.handoff_phase_status import phase_tasks_progress  # noqa: E402
from lib.phase_quality import phase_is_engaged  # noqa: E402
from tests.conftest import _phase_status  # noqa: E402


def test_legacy_completed_steps_only_config_merges_into_driven_run(tmp_path):
    legacy = {
        "standalone": True,
        "pipeline": ["project", "design", "plan", "build"],
        "status": "in_progress",
        "current_step": "design",
        "completed_steps": ["project"],
    }
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps(legacy), encoding="utf-8",
    )

    config = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_path)

    assert _phase_status(config, "project") in ("done", "skipped")


def test_a_phase_tasks_present_config_never_consults_completed_steps(tmp_path):
    """A config that HAS *usable* phase_tasks[] -- even a genuinely mid-flight
    one where nothing has finished YET (the shape every post-s5 standalone run
    can be caught in) -- must never fall back to a stale/disagreeing
    ``completed_steps``: only the total absence of usable ``phase_tasks[]``
    data triggers the legacy fallback above (external code review, GLM HIGH --
    the first version of this test asserted only ``!= "done"``, which the
    fallback's original buggy trigger -- firing on an EMPTY completed set,
    not on usable-entries absence -- still passed, because it merged the
    stale ``completed_steps`` in as ``"skipped"``, not ``"done"``)."""
    legacy = {
        "standalone": True,
        "pipeline": ["project", "design"],
        "status": "in_progress",
        "completed_steps": ["project", "design"],  # stale, must be ignored
        "phase_tasks": [{"phase": "project", "splitId": None, "status": "in_progress"}],
    }
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps(legacy), encoding="utf-8",
    )

    config = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_path)

    completed = phase_tasks_progress(config)[1]
    assert "project" not in completed
    assert "design" not in completed
    assert _phase_status(config, "project") not in ("done", "skipped")


def test_merged_project_engages_phase_quality_same_as_its_siblings(tmp_path):
    """A standalone-completed 'project' merged into a driven run must engage
    Phase-Quality exactly like its equally-completed siblings (external code
    review, GLM MEDIUM): _engagement.py's completed_steps/current_step
    OR-fallback that used to compensate for 'project's status=skipped,
    executionCount=0 shape is gone (s5) -- config_factory must now stamp
    executionCount=1 on it directly, matching build_v1_phase_task's "done"
    entries for the other merged phases."""
    legacy = {
        "standalone": True,
        "pipeline": ["project", "design", "plan", "build"],
        "status": "in_progress",
        "phase_tasks": [
            {"phase": "project", "splitId": None, "status": "done"},
            {"phase": "design", "splitId": None, "status": "done"},
        ],
    }
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps(legacy), encoding="utf-8",
    )

    config = create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", tmp_path)

    assert phase_is_engaged("project", config, []) == phase_is_engaged("design", config, [])
    assert phase_is_engaged("project", config, []) is True
