"""Tests for state management."""

import json

from lib.state import _phase_tasks_progress, detect_current_phase, get_checkpoint, has_handoff


class TestPhaseTasksProgress:
    """``_phase_tasks_progress`` is ``detect_current_phase``'s primary signal
    (campaign p4-04-retire-write-once-steps, sub-iterate s3)."""

    def test_malformed_status_does_not_crash(self):
        """A non-string status is neither finished nor absent, so the phase
        reads as CURRENT (not confidently complete) rather than vanishing —
        mirrors shared/scripts/lib/handoff_phase_status.status_of()'s guard
        against an unhashable `x in frozenset` check."""
        run = {"phase_tasks": [{"phase": "build", "status": ["done"]}]}
        current, completed = _phase_tasks_progress(run)
        assert current == "build"
        assert completed == set()

    def test_backlog_only_phase_counts_as_current(self):
        """A phase whose only phase_tasks[] entry is still queued
        (backlog/awaiting_launch) counts as CURRENT, not merely 'no
        confident signal' — external plan review flagged an earlier version
        that required an ACTIVE status, which would fall back to a
        config-heuristic for a run mid-transition (successor task planned
        but not yet claimed) that is otherwise perfectly healthy."""
        run = {
            "pipeline": ["project", "build"],
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "build", "status": "backlog"},
            ],
        }
        current, completed = _phase_tasks_progress(run)
        assert current == "build"
        assert completed == {"project"}

    def test_schema_version_run_with_all_entries_finished_derives_next_uncovered_phase(
        self,
    ):
        """Doubt review, sub-iterate s3: `recover_phase_task(force_status=
        "skipped")` (the operator's manual escape hatch) can terminalize a
        phase WITHOUT planning a successor -- every present entry finished,
        pipeline not fully covered, no entry at all for the true next phase.
        `schemaVersion` (written on every driven v2 run by config_factory,
        never on a v1-only config) distinguishes this from the
        by-shape-identical hybrid/standalone case
        (test_detect_phase_falls_back_to_heuristic_when_next_phase_not_yet_planned
        below has no schemaVersion and must still fall through to the
        heuristic, unaffected by this branch)."""
        run = {
            "schemaVersion": 2,
            "pipeline": ["project", "design", "plan", "build", "test"],
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "design", "status": "done"},
                {"phase": "plan", "status": "done"},
                {"phase": "build", "status": "skipped"},
            ],
        }
        current, completed = _phase_tasks_progress(run)
        assert current == "test"
        assert completed == {"project", "design", "plan", "build"}

    def test_untagged_run_with_same_shape_does_not_derive_next_phase(self):
        """Same all-finished/pipeline-uncovered shape as above, but no
        `schemaVersion` — must stay `None` (falls through to the caller's own
        heuristic/v1 fallback), since this shape is indistinguishable from a
        hybrid/standalone config without the discriminator."""
        run = {
            "pipeline": ["project", "design", "plan", "build", "test"],
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "design", "status": "done"},
                {"phase": "plan", "status": "done"},
                {"phase": "build", "status": "skipped"},
            ],
        }
        current, completed = _phase_tasks_progress(run)
        assert current is None
        assert completed == {"project", "design", "plan", "build"}


def test_detect_phase_not_started(tmp_project):
    assert detect_current_phase(tmp_project) == "not_started"


def test_detect_phase_v1_only_completed_steps_covers_pipeline_is_complete(tmp_project):
    """A v1-only (no phase_tasks[]) run whose completed_steps covers the
    whole declared pipeline must read "complete" — external code review,
    campaign p4-04-retire-write-once-steps sub-iterate s3: the config-only
    heuristic fallback has no terminal "complete" state of its own (it only
    ever returns a phase name or "not_started"), so dropping this narrow
    completed_steps-based check regressed a genuinely-finished standalone
    run to reporting a phase name instead."""
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({
            "pipeline": ["project", "design", "plan", "build"],
            "completed_steps": ["project", "design", "plan", "build"],
        }),
        encoding="utf-8",
    )
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-x", "status": "complete"}]}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "complete"


def test_detect_phase_v1_only_mid_pipeline_reads_live_current_step(tmp_project):
    """A v1-only (no phase_tasks[]) run past `build` must read the live
    `current_step` `update_step` maintains for standalone runs, not fall to
    the config heuristic -- which has no way to express test/changelog/
    deploy at all and would misreport "build" (code review, campaign
    p4-04-retire-write-once-steps, sub-iterate s3: an earlier version
    dropped this read entirely)."""
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({
            "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
            "current_step": "changelog",
            "completed_steps": ["project", "design", "plan", "build", "test"],
        }),
        encoding="utf-8",
    )
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-x", "status": "complete"}]}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "changelog"


def test_detect_phase_build(project_with_configs):
    """Fixture has no phase_tasks[] (v1-only shape) — falls back to the
    build_config heuristic (01-layout complete, 02-widgets in_progress),
    which happens to agree with the fixture's stale current_step=build."""
    assert detect_current_phase(project_with_configs) == "build"


def test_detect_phase_from_phase_tasks(project_with_configs):
    """Primary path: reads the current phase from phase_tasks[], not
    current_step (campaign p4-04-retire-write-once-steps, sub-iterate s3)."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["phase_tasks"] = [
        {"phase": "project", "status": "done"},
        {"phase": "design", "status": "done"},
        {"phase": "plan", "status": "done"},
        {"phase": "build", "status": "done"},
        {"phase": "test", "status": "done"},
        {"phase": "changelog", "status": "done"},
        {"phase": "deploy", "status": "in_progress"},
    ]
    run_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "deploy"


def test_detect_phase_phase_tasks_ignores_stale_current_step(project_with_configs):
    """current_step/completed_steps are write-once and claim 'build' here,
    while phase_tasks[] says deploy is actually running — phase_tasks[] must
    win (campaign p4-04-retire-write-once-steps)."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    assert config["current_step"] == "build"  # fixture's stale claim, unchanged
    config["phase_tasks"] = [
        {"phase": "project", "status": "done"},
        {"phase": "design", "status": "done"},
        {"phase": "plan", "status": "done"},
        {"phase": "build", "status": "done"},
        {"phase": "test", "status": "done"},
        {"phase": "changelog", "status": "done"},
        {"phase": "deploy", "status": "in_progress"},
    ]
    run_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "deploy"


def test_detect_phase_complete_from_phase_tasks(project_with_configs):
    """All pipeline phases finished in phase_tasks[] → complete, even though
    current_step/completed_steps (write-once) still claim 'build'/partial."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["phase_tasks"] = [
        {"phase": phase, "status": "done"} for phase in config["pipeline"]
    ]
    run_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "complete"


def test_detect_phase_backlog_entry_counts_as_current_not_a_fallback(project_with_configs):
    """A phase_tasks[] entry that is still queued (backlog/awaiting_launch —
    materialized but not yet claimed) counts as CURRENT, not 'no confident
    signal' (external plan review, campaign p4-04-retire-write-once-steps,
    sub-iterate s3 — an earlier version required an ACTIVE status and fell
    through to the heuristic here, which would silently disagree with
    phase_tasks[] the moment the successor task is planned but not yet
    claimed)."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["phase_tasks"] = [
        {"phase": "project", "status": "done"},
        {"phase": "design", "status": "done"},
        {"phase": "plan", "status": "done"},
        {"phase": "build", "status": "backlog"},
    ]
    run_path.write_text(json.dumps(config))

    assert detect_current_phase(project_with_configs) == "build"


def test_detect_phase_falls_back_to_heuristic_when_next_phase_not_yet_planned(
    project_with_configs,
):
    """phase_tasks[] is confident about 'project' (done) but has no entry at
    all yet for the true frontier phase — current stays None (nothing
    matches "has an entry, not complete"), and the partial completed set
    doesn't cover the whole pipeline either, so this falls through to the
    heuristic, exactly as an absent phase_tasks[] does."""
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["phase_tasks"] = [{"phase": "project", "status": "done"}]
    run_path.write_text(json.dumps(config))

    # Falls back to the build_config heuristic (01-layout complete,
    # 02-widgets in_progress) → "build", same as the no-phase_tasks case.
    assert detect_current_phase(project_with_configs) == "build"


def test_detect_phase_fallback_heuristic(tmp_project):
    """Without current_step in run_config, falls back to heuristic."""
    # Minimal run_config without current_step
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-x", "status": "in_progress"}]}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "build"


def test_detect_phase_standalone_project_in_progress(tmp_project):
    """Standalone: only project_config with in_progress → returns 'project'."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "in_progress", "scope": "full_app"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "project"


def test_detect_phase_standalone_project_complete(tmp_project):
    """Standalone: project complete → returns 'design' (next step)."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "design"


def test_detect_phase_standalone_design_in_progress(tmp_project):
    """Standalone: design in progress (flag in project_config) → returns 'design'."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "design_phase": "in_progress"}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "design"


def test_detect_phase_standalone_design_complete(tmp_project):
    """Standalone: design complete → returns 'plan' (next step)."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "design_phase": "complete"}),
        encoding="utf-8",
    )
    assert detect_current_phase(tmp_project) == "plan"


def test_detect_phase_standalone_plan_in_progress(tmp_project):
    """Standalone: plan in progress → returns 'plan'."""
    (tmp_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "design_phase": "complete"}),
        encoding="utf-8",
    )
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "in_progress"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "plan"


def test_detect_phase_standalone_plan_complete(tmp_project):
    """Standalone: plan complete → returns 'build' (next step)."""
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    assert detect_current_phase(tmp_project) == "build"


def test_detect_phase_stale_build_config_skipped(tmp_project):
    """Stale build config with all-complete sections is ignored."""
    (tmp_project / "shipwright_plan_config.json").write_text(
        json.dumps({"status": "in_progress"}), encoding="utf-8"
    )
    (tmp_project / "shipwright_build_config.json").write_text(
        json.dumps({"sections": [{"name": "01-x", "status": "complete"}]}),
        encoding="utf-8",
    )
    # Plan in_progress should win over stale completed build
    assert detect_current_phase(tmp_project) == "plan"


def test_get_checkpoint_empty(tmp_project):
    checkpoint = get_checkpoint(tmp_project)
    assert checkpoint["phase"] == "not_started"
    assert checkpoint["has_run_config"] is False


def test_get_checkpoint_with_data(project_with_configs):
    checkpoint = get_checkpoint(project_with_configs)
    assert checkpoint["phase"] == "build"
    assert checkpoint["has_run_config"] is True
    assert checkpoint["total_splits"] == 2
    assert checkpoint["completed_splits"] == 1
    assert checkpoint["current_split"] == "02-dashboard"
    assert checkpoint["total_sections"] == 2
    assert checkpoint["completed_sections"] == 1
    assert checkpoint["current_section"] == "02-widgets"


def test_get_checkpoint_splits_from_run_config(project_with_configs):
    """Checkpoint reads completed_splits from run_config, not project_config."""
    # Update run_config to mark both splits complete
    run_path = project_with_configs / "shipwright_run_config.json"
    config = json.loads(run_path.read_text())
    config["completed_splits"] = ["01-auth", "02-dashboard"]
    run_path.write_text(json.dumps(config))

    checkpoint = get_checkpoint(project_with_configs)
    assert checkpoint["completed_splits"] == 2
    assert checkpoint["current_split"] is None


def test_has_handoff_false(tmp_project):
    assert has_handoff(tmp_project) is False


def test_has_handoff_true(tmp_project):
    handoff = tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md"
    handoff.write_text("# Handoff")
    assert has_handoff(tmp_project) is True
