"""Direct coverage for the review-record → marker verdict contract. @FR-01.11"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.review_companion import repair_markers, write_markers
from lib.review_findings import ReviewFindingsError
from lib import review_payloads
from lib.review_payloads import build_review_evidence, build_reviewer_verdicts
from lib.review_record import (
    STATUS_COMPLETED,
    make_entry,
    new_record,
    upsert_review,
    write_record,
)
from lib.review_record_core import ReviewRecordError
from lib.review_record_schema import validate_entry
from tools import record_review_pass


def _external_payload(
    tmp_path: Path, *, schema: int | None = 2, first: str = "deepseek",
    second_verdict: str = "revise",
) -> Path:
    payload = {
        "success": True,
        "reviews": {
            first: {
                "status": "success",
                "feedback": "No findings.\n\nSHIPWRIGHT_VERDICT: approve",
            },
            "openai": {
                "status": "success",
                "feedback": f"One refinement.\n\nSHIPWRIGHT_VERDICT: {second_verdict}",
            },
        },
    }
    if schema is not None:
        payload["review_schema"] = schema
    path = tmp_path / f"{first}-{schema}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_current_and_historical_payloads_derive_their_real_verdict_pairs(tmp_path):
    current = build_reviewer_verdicts(
        "external-review-json", str(_external_payload(tmp_path))
    )
    historical = build_reviewer_verdicts(
        "external-review-json",
        str(_external_payload(tmp_path, schema=None, first="gemini")),
    )
    assert current == {"deepseek": "approve", "openai": "revise"}
    assert historical == {"gemini": "approve", "openai": "revise"}


def test_non_external_payload_has_no_reviewer_verdict_contract():
    assert build_reviewer_verdicts("code-reviewer", None) is None


def test_combined_evidence_reads_the_payload_once(monkeypatch):
    payload = json.dumps({
        "review_schema": 2,
        "reviews": {
            "deepseek": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"},
            "openai": {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: reject"},
        },
    })
    reads = []
    monkeypatch.setattr(review_payloads, "_read", lambda path: reads.append(path) or payload)
    *_, verdicts = build_review_evidence("external-review-json", "review.json")
    assert reads == ["review.json"]
    assert verdicts == {"deepseek": "approve", "openai": "reject"}


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"review_schema": 2}, "no 'reviews' object"),
        ({"review_schema": 99, "reviews": {}}, "unsupported external review schema"),
        ({"review_schema": 2, "reviews": {"gemini": {}, "openai": {}}},
         "does not match reviewer roster"),
    ],
)
def test_malformed_external_envelopes_fail_closed(tmp_path, payload, error):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReviewFindingsError, match=error):
        build_reviewer_verdicts("external-review-json", str(path))


def test_missing_external_payload_fails_closed():
    with pytest.raises(ReviewFindingsError, match="requires --payload-file"):
        build_reviewer_verdicts("external-review-json", None)


@pytest.mark.parametrize(
    "verdicts,error",
    [
        ("approve", "must be an object"),
        ({"foo": "approve", "openai": "approve"}, "unsupported reviewer set"),
        ({"deepseek": "maybe", "openai": "approve"}, "unknown verdict"),
    ],
)
def test_review_record_rejects_malformed_verdict_evidence(verdicts, error):
    entry = make_entry("plan", STATUS_COMPLETED)
    entry["verdicts"] = verdicts
    assert error in (validate_entry("plan", entry) or "")


def test_companion_writes_and_repairs_from_the_recorded_verdicts(tmp_path):
    current = {"deepseek": "approve", "openai": "revise"}
    paths = write_markers(
        tmp_path, "run-1", "plan", marker_status="completed",
        findings_count=0, verdicts=current,
    )
    marker = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert marker["marker_schema"] == 3
    assert marker["verdicts"] == current

    record = upsert_review(
        new_record("run-1"),
        make_entry("plan", STATUS_COMPLETED, verdicts=current),
    )
    write_record(tmp_path, "run-1", record)
    Path(paths[0]).unlink()
    repaired = repair_markers(
        tmp_path, "run-1", "plan", marker_status="completed"
    )
    assert json.loads(Path(repaired[0]).read_text(encoding="utf-8"))["verdicts"] == current


def test_companion_repairs_the_recorded_operator_resolution(tmp_path):
    verdicts = {"deepseek": "approve", "openai": "reject"}
    resolution = "Operator accepted OpenAI rejection and corrected the implementation."
    paths = write_markers(
        tmp_path, "run-1", "plan", marker_status="completed", findings_count=1,
        verdicts=verdicts, contradiction_resolution=resolution,
    )
    record = upsert_review(new_record("run-1"), make_entry(
        "plan", STATUS_COMPLETED, verdicts=verdicts,
        contradiction_resolution=resolution,
    ))
    write_record(tmp_path, "run-1", record)
    Path(paths[0]).unlink()
    repaired = repair_markers(tmp_path, "run-1", "plan", marker_status="completed")
    marker = json.loads(Path(repaired[0]).read_text(encoding="utf-8"))
    assert marker["contradiction_resolution"] == resolution


def test_completed_companion_without_verdicts_is_refused(tmp_path):
    with pytest.raises(ReviewRecordError, match="requires reviewer verdicts"):
        write_markers(
            tmp_path, "run-1", "plan", marker_status="completed", findings_count=0
        )


def test_record_cli_main_dual_writes_verdicts_in_process(tmp_path, capsys):
    payload = _external_payload(tmp_path, second_verdict="reject")
    resolution = "Operator accepted OpenAI rejection and corrected the implementation."
    assert record_review_pass.main([
        "init", "--project-root", str(tmp_path), "--run-id", "run-1",
    ]) == 0
    capsys.readouterr()
    assert record_review_pass.main([
        "record", "--project-root", str(tmp_path), "--run-id", "run-1",
        "--review-type", "plan", "--status", "completed",
        "--marker-status", "completed", "--from", "external-review-json",
        "--payload-file", str(payload), "--provider", "openrouter",
        "--contradiction-resolution", resolution,
    ]) == 0
    marker = json.loads(
        (tmp_path / ".shipwright" / "planning" / "iterate" / "run-1"
         / "external_review_state.json").read_text(encoding="utf-8")
    )
    assert marker["verdicts"] == {"deepseek": "approve", "openai": "reject"}
    assert marker["contradiction_resolution"] == resolution
    record = json.loads(
        (tmp_path / ".shipwright" / "planning" / "iterate" / "run-1"
         / "reviews.json").read_text(encoding="utf-8")
    )
    assert record["reviews"]["plan"]["contradiction_resolution"] == resolution
    marker_path = (tmp_path / ".shipwright" / "planning" / "iterate" / "run-1"
                   / "external_review_state.json")
    marker_path.unlink()
    assert record_review_pass.main([
        "repair-markers", "--project-root", str(tmp_path), "--run-id", "run-1",
        "--review-type", "plan", "--marker-status", "completed",
    ]) == 0
    repaired = json.loads(marker_path.read_text(encoding="utf-8"))
    assert repaired["contradiction_resolution"] == resolution
