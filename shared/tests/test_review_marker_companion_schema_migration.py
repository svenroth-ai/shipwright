"""Marker-schema migration coverage: historical rosters + unrecognized rosters. @FR-01.11"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.review_companion import repair_markers, write_markers
from lib.review_marker import STATE_BLOCK, evaluate_review_state
from lib.review_record import STATUS_COMPLETED, make_entry, new_record, upsert_review, write_record
from lib.review_record_core import ReviewRecordError


def test_companion_writes_and_repairs_a_historical_deepseek_envelope_as_schema_3(tmp_path):
    # Regression: write_markers used to fall back to MARKER_SCHEMA (4) for any
    # non-gemini roster, so repairing a pre-swap deepseek/openai record wrote
    # a schema-4 marker carrying a deepseek roster - which evaluate_review_state
    # then blocks, since schema 4 requires glm/openai. A historical record must
    # stay both readable AND writable/repairable as schema 3.
    historical = {"deepseek": "approve", "openai": "revise"}
    paths = write_markers(
        tmp_path, "run-1", "plan", marker_status="completed",
        record_status="completed", findings_count=0, verdicts=historical,
    )
    marker = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert marker["marker_schema"] == 3
    assert marker["verdicts"] == historical
    state, _ = evaluate_review_state(marker)
    assert state != STATE_BLOCK

    record = upsert_review(
        new_record("run-1"),
        make_entry("plan", STATUS_COMPLETED, verdicts=historical),
    )
    write_record(tmp_path, "run-1", record)
    Path(paths[0]).unlink()
    repaired = repair_markers(
        tmp_path, "run-1", "plan", marker_status="completed"
    )
    repaired_marker = json.loads(Path(repaired[0]).read_text(encoding="utf-8"))
    assert repaired_marker["marker_schema"] == 3
    assert repaired_marker["verdicts"] == historical


def test_companion_writes_a_historical_gemini_envelope_as_schema_2(tmp_path):
    historical = {"gemini": "approve", "openai": "revise"}
    paths = write_markers(
        tmp_path, "run-1", "plan", marker_status="completed",
        record_status="completed", findings_count=0, verdicts=historical,
    )
    marker = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert marker["marker_schema"] == 2
    assert marker["verdicts"] == historical
    state, _ = evaluate_review_state(marker)
    assert state != STATE_BLOCK


def test_write_markers_rejects_an_unrecognized_verdict_roster(tmp_path):
    # A gateway-route pair (GATEWAY_REVIEWERS = "model-1"/"model-2") or any
    # other unrecognized reviewer set must fail loudly here rather than fall
    # through to MARKER_SCHEMA silently, mirroring the fix that now applies
    # to the historical deepseek/openai roster.
    with pytest.raises(ReviewRecordError, match="unrecognized reviewer set"):
        write_markers(
            tmp_path, "run-1", "plan", marker_status="completed",
            record_status="completed", findings_count=0,
            verdicts={"model-1": "approve", "model-2": "approve"},
        )
