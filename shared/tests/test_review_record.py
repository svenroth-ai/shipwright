"""Tests for shared/scripts/lib/review_record.py — the per-run review record.

Covers the record shape (AC2), the immutability guard (AC3), strict schema
validation (external plan review O5), and create-if-absent `init` (AC9).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    SCHEMA_VERSION,
    ImmutableReviewError,
    ReviewRecordError,
    init_record,
    make_entry,
    new_record,
    pending_types,
    read_record,
    record_path,
    upsert_review,
    validate_record,
    write_record,
)

RUN_ID = "iterate-2026-07-21-review-record"
REASON = "not applicable at trivial complexity per the phase matrix"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    return tmp_path


# --- shape (AC2) ------------------------------------------------------------


def test_new_record_materializes_all_five_types_as_pending():
    rec = new_record(RUN_ID)
    assert set(rec["reviews"]) == set(REVIEW_TYPES)
    assert len(REVIEW_TYPES) == 5
    for review_type in REVIEW_TYPES:
        entry = rec["reviews"][review_type]
        assert entry["status"] == "pending"
        assert entry["review_type"] == review_type
        assert entry["findings"] == []
        assert entry["findings_count"] == 0
    assert rec["run_id"] == RUN_ID
    assert rec["schema_version"] == SCHEMA_VERSION


def test_pending_types_lists_only_unclosed_types():
    rec = new_record(RUN_ID)
    assert set(pending_types(rec)) == set(REVIEW_TYPES)
    rec = upsert_review(rec, make_entry("self", "completed"))
    assert "self" not in pending_types(rec)
    assert len(pending_types(rec)) == 4


def test_findings_count_is_derived_not_supplied():
    entry = make_entry(
        "code",
        "completed",
        findings=[
            {"finding": "a", "category": "correctness"},
            {"finding": "b", "category": "security"},
        ],
    )
    assert entry["findings_count"] == 2


# --- immutability (AC3) -----------------------------------------------------


@pytest.mark.parametrize("terminal", ["completed", "not_run", "not_applicable"])
def test_upsert_onto_terminal_status_is_rejected(terminal):
    rec = new_record(RUN_ID)
    rec = upsert_review(rec, make_entry("code", terminal, disposition=REASON))
    with pytest.raises(ImmutableReviewError):
        upsert_review(rec, make_entry("code", "completed"))


def test_force_overrides_the_immutability_guard():
    rec = new_record(RUN_ID)
    rec = upsert_review(rec, make_entry("code", "completed"))
    rec = upsert_review(
        rec, make_entry("code", "not_run", disposition=REASON), force=True
    )
    assert rec["reviews"]["code"]["status"] == "not_run"


def test_upsert_onto_pending_is_allowed():
    rec = new_record(RUN_ID)
    rec = upsert_review(rec, make_entry("plan", "completed"))
    assert rec["reviews"]["plan"]["status"] == "completed"


def test_rejected_upsert_leaves_the_file_byte_identical(project):
    rec = new_record(RUN_ID)
    rec = upsert_review(rec, make_entry("doubt", "completed"))
    write_record(project, RUN_ID, rec)
    before = record_path(project, RUN_ID).read_bytes()
    with pytest.raises(ImmutableReviewError):
        upsert_review(read_record(project, RUN_ID), make_entry("doubt", "not_run",
                                                               disposition=REASON))
    assert record_path(project, RUN_ID).read_bytes() == before


# --- strict validation (external plan review O5) ----------------------------


def test_validate_rejects_a_missing_review_type():
    rec = new_record(RUN_ID)
    del rec["reviews"]["doubt"]
    ok, err = validate_record(rec)
    assert not ok and "doubt" in err


def test_validate_rejects_an_unknown_review_type():
    rec = new_record(RUN_ID)
    rec["reviews"]["gut_feeling"] = make_entry("self", "completed")
    ok, err = validate_record(rec)
    assert not ok and "gut_feeling" in err


def test_validate_rejects_a_key_that_disagrees_with_its_review_type():
    rec = new_record(RUN_ID)
    rec["reviews"]["code"]["review_type"] = "doubt"
    ok, err = validate_record(rec)
    assert not ok


def test_validate_rejects_an_unknown_status():
    rec = new_record(RUN_ID)
    rec["reviews"]["code"]["status"] = "probably_fine"
    ok, err = validate_record(rec)
    assert not ok and "probably_fine" in err


def test_validate_rejects_findings_count_mismatch():
    rec = new_record(RUN_ID)
    rec["reviews"]["code"]["findings_count"] = 7
    ok, err = validate_record(rec)
    assert not ok


@pytest.mark.parametrize("bad", ["", "   ", "skipped", "n/a"])
def test_validate_rejects_a_blank_or_generic_disposition(bad):
    """A terminal non-completed status must NAME A RULE (AC2). A bare word is
    how 'nothing was reviewed' gets laundered into a passing gate."""
    rec = new_record(RUN_ID)
    rec["reviews"]["code"] = make_entry("code", "not_run", disposition=REASON)
    rec["reviews"]["code"]["disposition"] = bad
    ok, err = validate_record(rec)
    assert not ok


def test_validate_accepts_a_disposition_that_names_a_rule():
    rec = new_record(RUN_ID)
    rec = upsert_review(rec, make_entry("code", "not_run", disposition=REASON))
    ok, err = validate_record(rec)
    assert ok, err


def test_validate_rejects_a_run_id_mismatch():
    rec = new_record(RUN_ID)
    ok, err = validate_record(rec, expected_run_id="iterate-2026-01-01-other")
    assert not ok


def test_validate_rejects_a_future_schema_version():
    rec = new_record(RUN_ID)
    rec["schema_version"] = SCHEMA_VERSION + 1
    ok, err = validate_record(rec)
    assert not ok


def test_make_entry_rejects_a_terminal_non_completed_status_without_disposition():
    with pytest.raises(ReviewRecordError):
        make_entry("code", "not_run")


# --- init is create-if-absent (AC9) -----------------------------------------


def test_init_creates_the_record_when_absent(project):
    rec, created = init_record(project, RUN_ID)
    assert created is True
    assert record_path(project, RUN_ID).exists()
    assert set(rec["reviews"]) == set(REVIEW_TYPES)


def test_init_over_a_populated_record_changes_nothing(project):
    rec, _ = init_record(project, RUN_ID)
    rec = upsert_review(rec, make_entry("self", "completed"))
    write_record(project, RUN_ID, rec)
    before = record_path(project, RUN_ID).read_bytes()

    again, created = init_record(project, RUN_ID)

    assert created is False
    assert again["reviews"]["self"]["status"] == "completed"
    assert record_path(project, RUN_ID).read_bytes() == before


def test_init_over_a_corrupt_record_fails_rather_than_replacing_it(project):
    path = record_path(project, RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ReviewRecordError):
        init_record(project, RUN_ID)

    assert path.read_text(encoding="utf-8") == "{not json"


def test_read_record_returns_none_when_absent(project):
    assert read_record(project, RUN_ID) is None


def test_read_record_raises_on_a_schema_invalid_file(project):
    path = record_path(project, RUN_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "run_id": RUN_ID,
                                "reviews": {}}), encoding="utf-8")
    with pytest.raises(ReviewRecordError):
        read_record(project, RUN_ID)


def test_record_path_is_run_scoped(project):
    path = record_path(project, RUN_ID)
    assert path.name == "reviews.json"
    assert path.parent.name == RUN_ID
    assert path.parent.parent.name == "iterate"


# --- run_id is a path component (found in self-review) ----------------------


@pytest.mark.parametrize("hostile", [
    "../../../../etc/evil",
    "..",
    ".",
    "a/b",
    "a\\b",
    "C:/Windows/Temp/x",
    "/absolute/path",
    "",
    "-leading-dash-is-fine-but-not-this/..",
    "x" * 129,
])
def test_record_dir_refuses_an_unsafe_run_id(project, hostile):
    """``run_id`` becomes a directory name. An absolute value would silently
    REPLACE project_root and a `..` value would climb out of the planning dir."""
    with pytest.raises(ReviewRecordError):
        record_path(project, hostile)


def test_an_unsafe_run_id_cannot_be_smuggled_in_through_the_file(project):
    rec = new_record(RUN_ID)
    rec["run_id"] = "../../elsewhere"
    ok, err = validate_record(rec)
    assert not ok and "safe" in err


def test_a_realistic_run_id_is_accepted(project):
    assert record_path(project, "iterate-2026-07-21-review-record").parent.name == RUN_ID
