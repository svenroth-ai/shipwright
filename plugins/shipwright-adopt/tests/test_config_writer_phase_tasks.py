"""Unit tests for config_writer.write_all's phase_tasks[] seeding.

Split out of test_config_writer.py (campaign p4-04-retire-write-once-steps s2,
bloat gate: the shared file crossed its 300-line limit) — a cohesive,
single-purpose group: the schema-shape probe and the real-consumer boundary
probe for the phase_tasks[] entries adopt seeds at adoption time.
"""

import importlib.util
import json
import re
import uuid
from pathlib import Path

import pytest

from lib.adopted_phase_tasks import build_adopted_phase_task
from lib.config_writer import write_all


def test_an_out_of_vocabulary_step_raises() -> None:
    """``write_all(..., completed_steps=[...])`` is a public keyword parameter,
    so a typo or a caller-supplied custom list must fail loud rather than
    silently mint a phase_tasks[] entry violating the schema's Phase enum and
    slashCommand pattern (caught in review at 3f-bis, campaign
    p4-04-retire-write-once-steps)."""
    with pytest.raises(ValueError, match="not a valid Phase"):
        build_adopted_phase_task("buidl", now="2026-09-09T00:00:00Z")


def test_write_all_propagates_the_same_guard_through_completed_steps(tmp_path: Path) -> None:
    """The public seam, not just the helper directly."""
    with pytest.raises(ValueError, match="not a valid Phase"):
        write_all(
            tmp_path,
            scope="full_app", profile="supabase-nextjs", split_name="01-adopted",
            plugin_version="0.1.0", dev_url=None, test_cmd=None, commit_sha=None,
            features_inferred=1, nested_excluded=[],
            fr_count=1, qr_count=0,
            completed_steps=["project", "buidl"],
        )


def test_phase_tasks_entries_satisfy_schema_required_fields(tmp_path: Path) -> None:
    """Boundary Probe: shared/schemas/run_config.v2.schema.json's PhaseTask
    ``required`` list + field shapes. Adopt does not run through the
    phase-task lifecycle (phase_task_lifecycle.py), so this is the only
    producer-side check that a seeded entry validates.

    Reads the ``required`` list and the two regex patterns straight out of
    the schema file (still no ``jsonschema`` dependency — this plugin is
    deliberately kept dependency-free, per ``enrichment_schema.py``'s own
    docstring) rather than restating them, so a schema change cannot drift
    silently past a hand-copied assertion here.
    """
    write_all(
        tmp_path,
        scope="full_app", profile="supabase-nextjs", split_name="01-adopted",
        plugin_version="0.1.0", dev_url=None, test_cmd=None, commit_sha=None,
        features_inferred=1, nested_excluded=[],
        fr_count=1, qr_count=0,
    )
    run_config = json.loads((tmp_path / "shipwright_run_config.json").read_text())

    repo_root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (repo_root / "shared" / "schemas" / "run_config.v2.schema.json").read_text(
            encoding="utf-8",
        ),
    )
    phase_task_def = schema["$defs"]["PhaseTask"]
    required = set(phase_task_def["required"])
    phase_task_id_re = re.compile(schema["$defs"]["PhaseTaskId"]["pattern"])
    slash_command_re = re.compile(phase_task_def["properties"]["slashCommand"]["pattern"])
    status_enum = set(schema["$defs"]["PhaseTaskStatus"]["enum"])

    for task in run_config["phase_tasks"]:
        assert required <= task.keys()
        assert phase_task_id_re.match(task["phaseTaskId"])
        assert task["splitId"] is None
        # sessionUuid must be a well-formed UUID string.
        uuid.UUID(task["sessionUuid"])
        assert task["version"] == 1
        assert task["status"] in status_enum
        # The meaningful status assertion (done/skipped) lives in
        # test_writes_all_configs_in_order; here we only pin schema validity.
        assert slash_command_re.match(task["slashCommand"])
        assert task["prerequisites"] == []
        assert task["executionCount"] == 0


def test_phase_tasks_read_as_complete_by_dashboard_phase_strip(tmp_path: Path) -> None:
    """Boundary Probe (producer -> file on disk -> consumer): the reader
    this campaign's decision (1) targets is
    plugins/shipwright-compliance/scripts/lib/mermaid.py's
    ``_get_phase_status`` (the dashboard phase strip, s1 of this campaign).
    An adopted repo's seeded phase_tasks[] must render EVERY completed_steps
    phase as 'complete', not 'pending' (AC1: does not look like it skipped
    phases) — loaded by file path, matching this repo's own cross-plugin
    `lib`-collision workaround (ADR-045).
    """
    write_all(
        tmp_path,
        scope="full_app", profile="supabase-nextjs", split_name="01-adopted",
        plugin_version="0.1.0", dev_url=None, test_cmd=None, commit_sha=None,
        features_inferred=1, nested_excluded=[],
        fr_count=1, qr_count=0,
    )
    run_config = json.loads((tmp_path / "shipwright_run_config.json").read_text())

    repo_root = Path(__file__).resolve().parents[3]
    mod_path = (
        repo_root / "plugins" / "shipwright-compliance" / "scripts" / "lib" / "mermaid.py"
    )
    spec = importlib.util.spec_from_file_location("mermaid_adopt_probe", mod_path)
    assert spec is not None and spec.loader is not None
    mermaid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mermaid)

    for phase in ("project", "plan", "build", "test"):
        status = mermaid._get_phase_status(phase, "complete", {"run": run_config})
        # pipeline_status == "complete" short-circuits to "complete" for
        # every phase, so also probe with a non-complete run status to
        # exercise the phase_tasks[]-driven branch specifically.
        assert status == "complete"
        status_in_progress_run = mermaid._get_phase_status(
            phase, "in_progress", {"run": run_config},
        )
        assert status_in_progress_run == "complete", (
            f"phase {phase!r} read as {status_in_progress_run!r} via phase_tasks[] — "
            "an adopted repo must not render as having skipped it"
        )

    # External-Code-Review-Findings (this sub-iterate): a reviewer flagged
    # that 'design' — in shipwright_run_config.json's `pipeline`, but never
    # in adopt's `completed_steps` default and so never seeded a phase_tasks[]
    # entry here — could render as pending, unlike project/plan/build/test.
    # Empirically false for a REAL adopted config: `write_run_config` always
    # stamps the run-level `status` "complete", and `_get_phase_status`
    # short-circuits on that BEFORE it ever looks at phase_tasks[] — a
    # behavior this diff does not touch. Proven here with the actual
    # produced `status` value, not the synthetic "in_progress" probe above.
    assert run_config["status"] == "complete"
    assert mermaid._get_phase_status("design", run_config["status"], {"run": run_config}) == "complete"
