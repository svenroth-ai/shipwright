"""``reason_code`` on review-record entries: schema, legacy reading, and the writers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402
from lib.review_entry_checks import default_disposition  # noqa: E402
from lib.review_record import STATUS_NOT_RUN, make_entry, new_record, validate_record  # noqa: E402


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def _record_with(entry_updates: dict, review_type: str = "code") -> dict:
    record = new_record(RUN_ID)
    entry = make_entry(review_type, STATUS_NOT_RUN, disposition="delegated to the campaign orchestrator")
    entry.update(entry_updates)
    record["reviews"][review_type] = entry
    return record


@pytest.mark.covers("FR-01.11")
def test_legacy_not_run_row_with_only_free_text_stays_valid():
    ok, error = validate_record(_record_with({}), expected_run_id=RUN_ID)
    assert ok, error


@pytest.mark.covers("FR-01.11")
def test_not_run_row_with_a_vocabulary_code_is_valid():
    ok, error = validate_record(_record_with({"reason_code": "unavailable"}), expected_run_id=RUN_ID)
    assert ok, error


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code", ["because", "", 7, "fixture-or-helper"])
def test_a_code_outside_the_review_family_is_refused(code):
    ok, error = validate_record(_record_with({"reason_code": code}), expected_run_id=RUN_ID)
    assert ok is False and "reason_code" in error


@pytest.mark.covers("FR-01.11")
def test_a_completed_row_cannot_carry_a_reason_code():
    record = new_record(RUN_ID)
    entry = make_entry("code", "completed")
    entry["reason_code"] = "unavailable"
    record["reviews"]["code"] = entry
    ok, error = validate_record(record, expected_run_id=RUN_ID)
    assert ok is False and "only meaningful on a not_run" in error


@pytest.mark.covers("FR-01.11")
def test_cli_records_a_code_and_synthesises_a_rule_naming_disposition(project):
    code, out = run_tool(project, "record", "--review-type", "external_code",
                         "--status", "not_run", "--reason-code", "user-opt-out")
    assert code == 0, out
    shown = json.loads(run_tool(project, "show")[1])
    row = shown["reviews"]["external_code"]
    assert row["reason_code"] == "user-opt-out"
    assert row["disposition"] == default_disposition("user-opt-out")


@pytest.mark.covers("FR-01.11")
def test_bare_code_synthesised_disposition_reaches_the_companion_marker(project):
    code, out = run_tool(project, "record", "--review-type", "external_code", "--status", "not_run",
                         "--reason-code", "user-opt-out", "--marker-status", "skipped_user_opt_out")
    assert code == 0, out
    markers = list((project / ".shipwright" / "planning" / "iterate" / RUN_ID).glob("external_*review_state.json"))
    assert markers, "no run-scoped marker written"
    assert default_disposition("user-opt-out") in markers[0].read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.11")
def test_cli_keeps_an_explicit_disposition_next_to_the_code(project):
    why = "no provider key configured for this project in external_review.json"
    code, out = run_tool(project, "record", "--review-type", "external_code", "--status", "not_run",
                         "--reason-code", "missing-keys", "--disposition", why)
    assert code == 0, out
    row = json.loads(run_tool(project, "show")[1])["reviews"]["external_code"]
    assert (row["reason_code"], row["disposition"]) == ("missing-keys", why)


@pytest.mark.covers("FR-01.11")
def test_cli_rejects_a_code_outside_the_vocabulary_and_one_on_a_completed_pass(project):
    code, out = run_tool(project, "record", "--review-type", "code", "--status", "not_run",
                         "--reason-code", "trust-me")
    assert code == 2 and "invalid choice" in out
    code, out = run_tool(project, "record", "--review-type", "self", "--status", "completed",
                         "--reason-code", "unavailable")
    assert code == 2 and "completed one has none" in out


@pytest.mark.covers("FR-01.11")
def test_cli_without_a_code_behaves_exactly_as_before(project):
    code, out = run_tool(project, "record", "--review-type", "code", "--status", "not_run")
    assert code == 2 and "disposition" in out
    row_code, _ = run_tool(project, "record", "--review-type", "code", "--status", "not_run",
                           "--disposition", "delegated to the campaign orchestrator at 3f-bis")
    assert row_code == 0
    row = json.loads(run_tool(project, "show")[1])["reviews"]["code"]
    assert "reason_code" not in row


@pytest.mark.covers("FR-01.11")
def test_close_missing_accepts_a_code_instead_of_a_disposition(project):
    code, out = run_tool(project, "close-missing", "--status", "not_run", "--reason-code", "trivial-auto")
    assert code == 0, out
    reviews = json.loads(run_tool(project, "show")[1])["reviews"]
    assert reviews and all(r["reason_code"] == "trivial-auto" for r in reviews.values())


@pytest.mark.covers("FR-01.11")
def test_close_missing_still_needs_one_of_disposition_or_code(project):
    code, out = run_tool(project, "close-missing", "--status", "not_run")
    assert code == 2 and "--disposition or --reason-code" in out
