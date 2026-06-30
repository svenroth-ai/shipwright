"""Unit tests for ``lib.triage_validate`` — the triage-log validator + orphan-status
classifier extracted from ``churn_merge`` (iterate-2026-06-30-sweep-outbox-quarantine-orphans).

Covers the classifier the outbox sweep relies on to distinguish the recoverable
orphan-status class from genuine corruption, and pins that ``validate_triage_text``'s
string-error API is unchanged (and still re-exported from ``churn_merge``).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.triage_validate import (  # noqa: E402
    TriageValidation,
    classify_triage_text,
    validate_triage_text,
)

HEADER = '{"v":1,"schema":"triage","created":"2026-06-08T00:00:00Z"}'
APPEND = '{"event":"append","id":"trg-a","status":"triage"}'
ORPHAN = '{"event":"status","id":"trg-ghost","newStatus":"dismissed"}'


def _log(*lines: str) -> str:
    return "\n".join([HEADER, *lines]) + "\n"


def test_clean_log_has_no_errors() -> None:
    v = classify_triage_text(_log(APPEND))
    assert isinstance(v, TriageValidation)
    assert v.errors == []
    assert v.orphan_status_ids == frozenset()
    assert v.has_non_orphan_error is False


def test_orphan_status_only_is_recoverable() -> None:
    v = classify_triage_text(_log(APPEND, ORPHAN))
    assert v.errors  # the orphan IS reported as an error...
    assert v.orphan_status_ids == frozenset({"trg-ghost"})  # ...but classified recoverable
    assert v.has_non_orphan_error is False


def test_status_with_matching_append_is_clean() -> None:
    # A status whose append exists (order-insensitive) is NOT an orphan.
    paired = '{"event":"status","id":"trg-a","newStatus":"dismissed"}'
    v = classify_triage_text(_log(APPEND, paired))
    assert v.errors == [] and v.orphan_status_ids == frozenset()


def test_invalid_json_is_non_orphan_error() -> None:
    v = classify_triage_text(_log(APPEND, '{"event":"status" BROKEN'))
    assert v.has_non_orphan_error is True


def test_duplicate_append_is_non_orphan_error() -> None:
    v = classify_triage_text(_log(APPEND, APPEND.replace("triage", "open")))
    # two appends, same id, different content (dedup not applied here) → duplicate
    assert v.has_non_orphan_error is True


def test_missing_header_is_non_orphan_error() -> None:
    v = classify_triage_text(APPEND + "\n")  # first line is not the header
    assert v.has_non_orphan_error is True


def test_mixed_orphan_and_corruption_flags_both() -> None:
    v = classify_triage_text(_log(APPEND, ORPHAN, '{"event":"append" BROKEN'))
    assert v.orphan_status_ids == frozenset({"trg-ghost"})
    assert v.has_non_orphan_error is True  # corruption present → caller must hard-block


def test_validate_triage_text_projects_classifier_strings() -> None:
    text = _log(APPEND, ORPHAN)
    assert validate_triage_text(text) == list(classify_triage_text(text).errors)


def test_validate_triage_text_reexported_from_churn_merge() -> None:
    from lib.churn_merge import classify_triage_text as cm_classify
    from lib.churn_merge import validate_triage_text as cm_validate

    assert cm_validate is validate_triage_text
    assert cm_classify is classify_triage_text
