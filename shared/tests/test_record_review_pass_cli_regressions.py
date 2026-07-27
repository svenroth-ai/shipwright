"""Regressions found in this tool's own code-review round.

Split out of `test_record_review_pass_cli.py` when it stood at 496 lines
against a 300-line limit. Each case here pins a defect the review caught:
an out-of-vocabulary marker status, a marker type recorded without one, a
repair path that dead-ended, a corrupt record reported as a traceback, and
a partial merge that read as clean."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import (  # noqa: E402
    EXTERNAL_REVIEW_OUTPUT,
    REASON,
    RUN_ID,
    TOOL,
    payload,
    make_project,
    run_tool,
)

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.review_record import record_path  # noqa: E402,F401
from tools.verifiers.review_record_check import check_review_record  # noqa: E402,F401


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)

# --- regressions from the code-review round ---------------------------------


def test_an_out_of_vocabulary_marker_status_is_rejected(project, tmp_path):
    """mark-review-state.py rejects these; recording through the new tool must
    not quietly lose that check and write a marker no consumer understands."""
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "complete",  # typo for "completed"
        "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT),
    )
    assert code == 2, output
    planning = project / ".shipwright" / "planning" / "iterate"
    assert not (planning / "external_review_state.json").exists()
    assert check_review_record(project, RUN_ID).ok is False


def test_recording_a_marker_type_as_completed_requires_a_marker_status(project, tmp_path):
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "external_code", "--status", "completed",
        "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT),
    )
    assert code == 2
    assert "marker-status is required" in output


def test_a_not_applicable_marker_type_needs_no_marker_status(project):
    """The marker vocabulary has no term for 'not applicable at this
    complexity'; forcing one would make the caller misstate why it did not run."""
    run_tool(project, "init")
    code, output = run_tool(project, "record", "--review-type", "external_code",
                            "--status", "not_applicable", "--disposition", REASON)
    assert code == 0, output


def test_repair_markers_rewrites_the_marker_without_touching_the_record(project, tmp_path):
    """The documented repair path: once the record is on disk it is immutable,
    so a failed marker write cannot be fixed by re-running `record`."""
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "plan", "--status", "completed",
             "--marker-status", "completed", "--from", "external-review-json",
             "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT))
    before = record_path(project, RUN_ID).read_bytes()
    planning = project / ".shipwright" / "planning" / "iterate"
    (planning / "external_review_state.json").unlink()

    code, output = run_tool(project, "repair-markers", "--review-type", "plan",
                            "--marker-status", "completed")

    assert code == 0, output
    assert (planning / "external_review_state.json").exists()
    assert record_path(project, RUN_ID).read_bytes() == before


def test_re_running_a_marker_bearing_record_repairs_instead_of_dead_ending(project, tmp_path):
    """Re-running the original command is what an operator actually does after a
    marker write fails; exit 3 with no way forward would be a dead end."""
    run_tool(project, "init")
    args = ["record", "--review-type", "plan", "--status", "completed",
            "--marker-status", "completed", "--from", "external-review-json",
            "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT)]
    run_tool(project, *args)
    planning = project / ".shipwright" / "planning" / "iterate"
    (planning / "external_review_state.json").unlink()

    code, output = run_tool(project, *args)

    assert code == 0, output
    assert json.loads(output).get("repaired") is True
    assert (planning / "external_review_state.json").exists()


def test_repair_markers_refuses_when_nothing_is_recorded_yet(project):
    run_tool(project, "init")
    code, output = run_tool(project, "repair-markers", "--review-type", "plan",
                            "--marker-status", "completed")
    assert code == 1
    assert "not recorded yet" in output


def test_init_over_a_corrupt_record_reports_json_not_a_traceback(project):
    """Every failure must exit through the JSON contract the orchestrator parses."""
    path = record_path(project, RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    code, output = run_tool(project, "init")

    assert code == 1
    assert json.loads(output)["error"] == "init_failed"
    assert path.read_text(encoding="utf-8") == "{not json"


def test_an_unsafe_run_id_is_reported_as_json(project):
    result = subprocess.run(
        [sys.executable, TOOL, "init", "--project-root", str(project),
         "--run-id", "../../escape"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["success"] is False


def test_a_leg_that_fails_to_parse_makes_the_merge_partial(project, tmp_path):
    """`structured` when only one of two legs parsed would hide that an entire
    provider's review was lost."""
    mixed = json.dumps({"success": True, "reviews": {
        "gemini": {"status": "success", "feedback":
                   "- Category: bug\n- Severity: high\n- Finding: a real defect\n"},
        "openai": {"status": "success", "feedback":
                   "I ran out of context mid-thought and never structured this"},
    }})
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "mixed.json", mixed),
    )

    assert code == 0, output
    assert json.loads(output)["parse_status"] == "partial"
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    plan = entry["reviews"]["plan"]
    assert plan["findings_count"] == 1
    assert "ran out of context" in plan["raw_excerpt"], (
        "the unparsed leg's own text must survive the shared excerpt budget"
    )
