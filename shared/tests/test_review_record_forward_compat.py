"""Forward-compatible review rows remain structurally strict. @FR-01.11"""

import pytest

from lib.review_record import STATUS_COMPLETED, make_entry, new_record, validate_record

RUN_ID = "iterate-2026-08-03-p2-33-deepseek-zdr-review"


def _stranger_entry(review_type: str = "deepseek") -> dict:
    entry = make_entry("plan", STATUS_COMPLETED, provider="openrouter")
    entry["review_type"] = review_type
    return entry


@pytest.mark.covers("FR-01.11/AC14")
def test_well_formed_stranger_review_key_is_readable():
    """AC14: a review record containing a reviewer type a current reader did
    not previously know remains readable when the entry is complete and
    internally consistent."""
    record = new_record(RUN_ID)
    record["reviews"]["deepseek"] = _stranger_entry()
    ok, error = validate_record(record, expected_run_id=RUN_ID)
    assert ok, error


@pytest.mark.covers("FR-01.11/AC14")
def test_stranger_key_and_review_type_must_match():
    record = new_record(RUN_ID)
    record["reviews"]["deepseek"] = _stranger_entry("gemini")
    ok, error = validate_record(record, expected_run_id=RUN_ID)
    assert ok is False
    assert "key says 'deepseek'" in error


@pytest.mark.covers("FR-01.11/AC14")
def test_malformed_stranger_entry_still_fails_closed():
    """AC14: a malformed entry still fails the integrity check."""
    record = new_record(RUN_ID)
    record["reviews"]["deepseek"] = _stranger_entry()
    record["reviews"]["deepseek"]["findings_count"] = 7
    ok, error = validate_record(record, expected_run_id=RUN_ID)
    assert ok is False
    assert "findings_count" in error


def test_stranger_key_does_not_become_required_for_new_records():
    record = new_record(RUN_ID)
    assert "deepseek" not in record["reviews"]
    ok, error = validate_record(record, expected_run_id=RUN_ID)
    assert ok, error
