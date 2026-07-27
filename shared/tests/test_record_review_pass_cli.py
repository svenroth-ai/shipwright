"""The `record_review_pass.py` CLI against its acceptance criteria.

AC8 is the important one: a real run across all five types, driven from the
payload shapes the reviewers actually emit, produces a record the F11 gate
then PASSES. Unit-testing the pieces separately would not have caught a CLI
that writes a record the gate rejects — the two must be exercised together.
Also covers immutability (AC3), the marker dual-write (AC7) and dispositions
(AC2). Regression groups live in the two sibling files; the shared fixture
and reviewer payloads in `_review_cli_harness.py`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import (  # noqa: E402
    CODE_REVIEWER_REPLY,
    DOUBT_REVIEWER_REPLY,
    EXTERNAL_REVIEW_OUTPUT,
    REASON,
    RUN_ID,
    SELF_REVIEW_REPLY,
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

# --- AC8: the whole path, CLI → gate ----------------------------------------


def test_recording_all_five_types_makes_the_gate_pass(project, tmp_path):
    assert check_review_record(project, RUN_ID).ok is False  # nothing recorded yet

    code, _ = run_tool(project, "init")
    assert code == 0

    for args in (
        ["record", "--review-type", "self", "--status", "completed",
         "--from", "self-review",
         "--payload-file", payload(tmp_path, "self.json", SELF_REVIEW_REPLY)],
        ["record", "--review-type", "code", "--status", "completed",
         "--from", "code-reviewer",
         "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY)],
        ["record", "--review-type", "doubt", "--status", "completed",
         "--from", "doubt-reviewer",
         "--payload-file", payload(tmp_path, "doubt.json", DOUBT_REVIEWER_REPLY)],
        ["record", "--review-type", "plan", "--status", "completed",
         "--from", "external-review-json", "--provider", "openrouter",
         "--marker-status", "completed",
         "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT)],
        ["record", "--review-type", "external_code", "--status", "not_applicable",
         "--disposition", REASON],
    ):
        code, output = run_tool(project, *args)
        assert code == 0, output

    result = check_review_record(project, RUN_ID)
    assert result.ok, result.detail

    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    reviews = record["reviews"]
    assert reviews["code"]["findings"][0]["severity"] == "high"
    assert reviews["code"]["findings"][0]["source"] == "code-reviewer"
    assert reviews["doubt"]["findings"][0]["category"] == "reversibility"
    assert reviews["self"]["findings_count"] == 1, "only the failed item is a finding"
    assert reviews["plan"]["findings_count"] == 2, "both provider legs are merged"
    assert reviews["external_code"]["status"] == "not_applicable"


# --- AC7: marker dual-write -------------------------------------------------


def test_a_plan_record_dual_writes_the_legacy_marker(project, tmp_path):
    run_tool(project, "init")
    code, output = run_tool(
        project, "record", "--review-type", "plan", "--status", "completed",
        "--from", "external-review-json", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, "ext.json", EXTERNAL_REVIEW_OUTPUT),
    )
    assert code == 0, output

    planning = project / ".shipwright" / "planning" / "iterate"
    shared_marker = planning / "external_review_state.json"
    run_scoped_marker = planning / RUN_ID / "external_review_state.json"

    assert shared_marker.exists(), "the historic shared path must keep working"
    assert run_scoped_marker.exists(), "the run-scoped copy is what the Mission view reads"
    assert json.loads(shared_marker.read_text(encoding="utf-8"))["status"] == "completed"
    assert json.loads(run_scoped_marker.read_text(encoding="utf-8"))["findings_count"] == 2


def test_a_marker_is_not_written_for_an_internal_type(project, tmp_path):
    run_tool(project, "init")
    code, _ = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--from", "code-reviewer", "--marker-status", "completed",
        "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY),
    )
    assert code == 2, "internal passes have no legacy marker — this is a usage error"


# --- AC3: immutability ------------------------------------------------------


def test_re_recording_a_terminal_type_exits_3(project, tmp_path):
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "code", "--status", "completed",
             "--from", "code-reviewer",
             "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY))
    before = record_path(project, RUN_ID).read_bytes()

    code, output = run_tool(project, "record", "--review-type", "code",
                            "--status", "not_run", "--disposition", REASON)

    assert code == 3, output
    assert json.loads(output)["error"] == "immutable"
    assert record_path(project, RUN_ID).read_bytes() == before


def test_force_overrides_immutability(project, tmp_path):
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "code", "--status", "completed",
             "--from", "code-reviewer",
             "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY))

    code, output = run_tool(project, "record", "--review-type", "code",
                            "--status", "not_run", "--disposition", REASON, "--force")

    assert code == 0, output


# --- AC2 / AC10: dispositions and the escape hatch --------------------------


def test_a_generic_disposition_is_rejected(project):
    run_tool(project, "init")
    code, output = run_tool(project, "record", "--review-type", "doubt",
                            "--status", "not_run", "--disposition", "skipped")
    assert code == 2
    assert "disposition" in output


def test_close_missing_closes_every_outstanding_type(project):
    """AC10 — a run past its review phases is one command from a COMPLETE record.
    NARROWED at medium+ by the code-review floor: writing the record no longer
    greens the gate — see `test_record_review_pass_cli_floor.py`."""
    assert check_review_record(project, RUN_ID).ok is False
    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the per-run review record")
    assert code == 0, output
    assert set(json.loads(output)["closed"]) == {
        "self", "plan", "code", "doubt", "external_code"}
    assert check_review_record(project, RUN_ID).detail.count("unanswered") == 0


def test_close_missing_leaves_already_recorded_types_alone(project, tmp_path):
    run_tool(project, "init")
    run_tool(project, "record", "--review-type", "code", "--status", "completed",
             "--from", "code-reviewer",
             "--payload-file", payload(tmp_path, "code.md", CODE_REVIEWER_REPLY))

    code, output = run_tool(project, "close-missing", "--status", "not_run",
                            "--disposition", "predates the per-run review record")

    assert code == 0
    assert "code" not in json.loads(output)["closed"]
    record = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))
    assert record["reviews"]["code"]["status"] == "completed"
    assert record["reviews"]["code"]["findings_count"] == 1


def test_close_missing_refuses_to_assert_completed_in_bulk(project):
    code, output = run_tool(project, "close-missing", "--status", "completed",
                            "--disposition", "everything was definitely reviewed")
    assert code == 2
    assert "cannot be asserted in bulk" in output
