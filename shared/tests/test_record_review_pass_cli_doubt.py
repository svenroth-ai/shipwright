"""Regressions found by the Stage-3 doubt pass.

Split out of `test_record_review_pass_cli.py` for the same reason as the
sibling regressions file. What these share is a theme rather than a
mechanism: each is a way the record could have reported something cleaner
than what happened — a restatement answered with success, a forced
correction leaving a stale marker, an unparseable review reaching the
marker as a clean zero, an errored provider dropped from the denominator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import (  # noqa: E402
    CODE_REVIEWER_REPLY,
    EXTERNAL_REVIEW_OUTPUT,
    REASON,
    RUN_ID,
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

# --- regressions from the Stage-3 doubt pass --------------------------------


def test_a_restatement_is_rejected_not_answered_with_success(project, tmp_path):
    """The repair shortcut used to convert ANY immutability rejection into exit 0
    whenever --marker-status was present, rewriting the marker from the new
    arguments — so the record could say `completed` with 17 findings while the
    marker said the pass was skipped, with no --force and a success exit code."""
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "plan", "--status", "completed",
             "--marker-status", "completed", "--from", "external-review-json",
             "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT))
    before = record_path(project, RUN_ID).read_bytes()
    planning = project / ".shipwright" / "planning" / "iterate"
    marker_before = (planning / "external_review_state.json").read_bytes()

    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "not_run",
        "--disposition", REASON, "--marker-status", "skipped_config_disabled",
    )

    assert code == 3, output
    assert json.loads(output)["error"] == "immutable"
    assert record_path(project, RUN_ID).read_bytes() == before
    assert (planning / "external_review_state.json").read_bytes() == marker_before


def test_a_forced_correction_must_also_restate_the_marker(project, tmp_path):
    """--force rewrote the record but could leave the marker asserting the
    superseded result, with nothing to invalidate it."""
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "plan", "--status", "completed",
             "--marker-status", "completed", "--from", "external-review-json",
             "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT))

    code, output = run_tool(project, "record", "--review-type", "plan",
                            "--status", "not_run", "--disposition", REASON, "--force")

    assert code == 2
    assert "requires --marker-status" in output


def test_an_unitemizable_review_does_not_reach_the_marker_as_a_clean_zero(project, tmp_path):
    """`status: completed, findings_count: 0` is read by the existing consumer as
    'ran and found nothing'. A review whose prose could not be itemized must
    carry the caveat in the one field that consumer surfaces."""
    unparseable = json.dumps({"success": True, "reviews": {
        "gemini": {"status": "success",
                   "feedback": "I reviewed it and have thoughts but wrote no structure"},
    }})
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "u.json", unparseable),
    )

    assert code == 0, output
    assert json.loads(output)["parse_status"] == "unstructured"
    marker = json.loads((project / ".shipwright" / "planning" / "iterate"
                         / "external_review_state.json").read_text(encoding="utf-8"))
    assert marker["findings_count"] == 0
    assert "NOT a clean-review result" in (marker["reason"] or "")


def test_a_provider_that_errored_counts_toward_the_denominator(project, tmp_path):
    """An errored leg carries no `feedback`, so filtering it out first let one
    good leg of two report `structured` — hiding the likelier loss mode."""
    errored = json.dumps({"success": True, "reviews": {
        "gemini": {"status": "success",
                   "feedback": "- Category: bug\n- Severity: high\n- Finding: a real defect\n"},
        "openai": {"status": "error", "reason": "rate limited"},
    }})
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", payload(tmp_path, "e.json", errored),
    )

    assert code == 0, output
    assert json.loads(output)["parse_status"] == "partial"
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert "rate limited" in entry["reviews"]["plan"]["raw_excerpt"]


def test_close_missing_can_be_scoped_to_named_types(project):
    """The blanket form permanently asserts 'did not run' for passes that did —
    the self-review always runs, at every complexity."""
    run_tool(project, "init")
    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the per-run review record",
                            "--only", "doubt,external_code")

    assert code == 0, output
    assert set(json.loads(output)["closed"]) == {"doubt", "external_code"}
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["self"]["status"] == "pending"


def test_close_missing_rejects_an_unknown_type(project):
    run_tool(project, "init")
    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the record", "--only", "vibes")
    assert code == 2
    assert "vibes" in output


def test_a_not_run_pass_records_no_findings_even_with_a_payload(project, tmp_path):
    """A payload attached to a pass that did not run would attribute findings to
    a review that never happened."""
    run_tool(project, "init")
    code, _ = run_tool(
        project, "record", "--review-type", "code", "--status", "not_run",
        "--disposition", REASON, "--from", "code-reviewer",
        "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY),
    )
    assert code == 0
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["code"]["findings"] == []
