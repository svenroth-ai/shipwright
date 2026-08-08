"""Pure-function tests for `lib.triage_amend` — vocabulary, validation,
event-building, and the pass-2 overlay. iterate-2026-08-08-triage-amend-event.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import triage_amend  # noqa: E402

SEVERITIES = ("critical", "high", "medium", "low", "info")
KINDS = ("bug", "feature", "improvement", "compliance", "maintenance")
PRIORITY_FROM_SEVERITY = {
    "critical": "P0", "high": "P1", "medium": "P2", "low": "P3", "info": "P3",
}


def _priority(severity: str) -> str:
    return PRIORITY_FROM_SEVERITY[severity]


# --- has_amend_content / build_amend_event --------------------------------

def test_has_amend_content_false_for_bare_envelope():
    assert triage_amend.has_amend_content({"event": "amend", "id": "trg-1"}) is False


@pytest.mark.parametrize("field", triage_amend.AMENDABLE_FIELDS)
def test_has_amend_content_true_for_each_amendable_field(field):
    assert triage_amend.has_amend_content({field: "x"}) is True


def test_build_amend_event_omits_absent_fields():
    event = triage_amend.build_amend_event("trg-1", "2026-08-08T00:00:00Z", "cli", title="New title")
    assert event == {
        "event": "amend", "id": "trg-1", "ts": "2026-08-08T00:00:00Z",
        "by": "cli", "title": "New title",
    }
    assert "detail" not in event and "severity" not in event and "kind" not in event


def test_build_amend_event_rejects_contentless_call():
    with pytest.raises(ValueError, match="amend must set at least one of"):
        triage_amend.build_amend_event("trg-1", "2026-08-08T00:00:00Z", "cli")


# --- check_amend_vocab ------------------------------------------------------

def test_check_amend_vocab_allows_absent_fields():
    triage_amend.check_amend_vocab(severity=None, kind=None, severities=SEVERITIES, kinds=KINDS)


def test_check_amend_vocab_rejects_unknown_severity():
    with pytest.raises(ValueError, match="unknown severity"):
        triage_amend.check_amend_vocab(severity="urgent", kind=None, severities=SEVERITIES, kinds=KINDS)


def test_check_amend_vocab_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown kind"):
        triage_amend.check_amend_vocab(severity=None, kind="epic", severities=SEVERITIES, kinds=KINDS)


# --- check_amend_title / check_amend_detail / check_amend_fields -----------

def test_check_amend_title_rejects_a_non_string():
    with pytest.raises(ValueError, match="title must be a non-empty string"):
        triage_amend.check_amend_title(42)


def test_check_amend_detail_allows_absent():
    triage_amend.check_amend_detail(None)


def test_check_amend_detail_rejects_a_non_string():
    with pytest.raises(ValueError, match="detail must be a string"):
        triage_amend.check_amend_detail(42)


def test_check_amend_fields_rejects_a_contentless_call():
    with pytest.raises(ValueError, match="amend must set at least one of"):
        triage_amend.check_amend_fields(
            title=None, detail=None, severity=None, kind=None, severities=SEVERITIES, kinds=KINDS,
        )


def test_check_amend_fields_passes_for_one_present_field():
    triage_amend.check_amend_fields(
        title="ok", detail=None, severity=None, kind=None, severities=SEVERITIES, kinds=KINDS,
    )


# --- resolve_amend_residence ------------------------------------------------

def test_resolve_amend_residence_raises_keyerror_for_unknown_id():
    with pytest.raises(KeyError):
        triage_amend.resolve_amend_residence(
            "trg-ghost", tracked_ids=set(), outbox_ids=set(), idle_main_routes_to_outbox=False,
        )


def test_resolve_amend_residence_tracked_preferred_when_in_both():
    to_outbox = triage_amend.resolve_amend_residence(
        "trg-1", tracked_ids={"trg-1"}, outbox_ids={"trg-1"}, idle_main_routes_to_outbox=False,
    )
    assert to_outbox is False


def test_resolve_amend_residence_outbox_only_routes_to_outbox():
    to_outbox = triage_amend.resolve_amend_residence(
        "trg-1", tracked_ids=set(), outbox_ids={"trg-1"}, idle_main_routes_to_outbox=False,
    )
    assert to_outbox is True


def test_resolve_amend_residence_idle_main_forces_outbox_even_if_tracked():
    to_outbox = triage_amend.resolve_amend_residence(
        "trg-1", tracked_ids={"trg-1"}, outbox_ids=set(), idle_main_routes_to_outbox=True,
    )
    assert to_outbox is True


# --- validate_amend_event ----------------------------------------------------

def test_validate_amend_event_true_when_all_present_fields_valid():
    raw = {"title": "ok", "severity": "high", "kind": "bug"}
    assert triage_amend.validate_amend_event(raw, severities=SEVERITIES, kinds=KINDS) is True


def test_validate_amend_event_true_for_field_absent_entirely():
    assert triage_amend.validate_amend_event({"detail": "d"}, severities=SEVERITIES, kinds=KINDS) is True


@pytest.mark.parametrize(
    "raw",
    [
        {"title": ""},
        {"title": "   "},
        {"title": 123},
        {"detail": 123},
        {"severity": "urgent"},
        {"kind": "epic"},
    ],
)
def test_validate_amend_event_false_for_any_invalid_present_field(raw):
    assert triage_amend.validate_amend_event(raw, severities=SEVERITIES, kinds=KINDS) is False


# --- apply_amend / try_apply_amend -------------------------------------------

def _base_item():
    return {
        "title": "old", "detail": "old detail", "severity": "low", "kind": "bug",
        "suggestedPriority": "P3", "ts": "2026-08-01T00:00:00Z",
        "amendedBy": None, "amendedAt": None,
    }


def test_apply_amend_overlays_only_present_fields():
    item = _base_item()
    raw = {"title": "new title", "by": "sven", "ts": "2026-08-08T00:00:00Z"}
    triage_amend.apply_amend(item, raw, priority_from_severity=_priority)
    assert item["title"] == "new title"
    assert item["detail"] == "old detail"  # absent field untouched
    assert item["severity"] == "low"


def test_apply_amend_never_touches_item_ts():
    item = _base_item()
    raw = {"title": "new title", "by": "sven", "ts": "2026-08-08T00:00:00Z"}
    triage_amend.apply_amend(item, raw, priority_from_severity=_priority)
    assert item["ts"] == "2026-08-01T00:00:00Z"


def test_apply_amend_severity_recomputes_suggested_priority():
    item = _base_item()
    raw = {"severity": "critical", "by": "sven", "ts": "2026-08-08T00:00:00Z"}
    triage_amend.apply_amend(item, raw, priority_from_severity=_priority)
    assert item["severity"] == "critical"
    assert item["suggestedPriority"] == "P0"


def test_apply_amend_kind_change_has_no_derived_field_side_effect():
    item = _base_item()
    item["suggestedDomain"] = "engineering"
    raw = {"kind": "compliance", "by": "sven", "ts": "2026-08-08T00:00:00Z"}
    triage_amend.apply_amend(item, raw, priority_from_severity=_priority)
    assert item["kind"] == "compliance"
    assert item["suggestedDomain"] == "engineering"  # untouched — derives from source, not kind


def test_apply_amend_records_amended_by_and_at():
    item = _base_item()
    raw = {"title": "new", "by": "sven", "ts": "2026-08-08T00:00:00Z"}
    triage_amend.apply_amend(item, raw, priority_from_severity=_priority)
    assert item[triage_amend.AMENDED_BY_FIELD] == "sven"
    assert item[triage_amend.AMENDED_AT_FIELD] == "2026-08-08T00:00:00Z"


def test_try_apply_amend_skips_whole_event_on_any_invalid_field():
    item = _base_item()
    raw = {"title": "should not apply", "severity": "urgent", "by": "x", "ts": "t"}
    triage_amend.try_apply_amend(item, raw, severities=SEVERITIES, kinds=KINDS, priority_from_severity=_priority)
    assert item["title"] == "old"
    assert item[triage_amend.AMENDED_BY_FIELD] is None


def test_try_apply_amend_applies_when_valid():
    item = _base_item()
    raw = {"title": "applied", "by": "x", "ts": "t"}
    triage_amend.try_apply_amend(item, raw, severities=SEVERITIES, kinds=KINDS, priority_from_severity=_priority)
    assert item["title"] == "applied"


def test_apply_amend_collapses_a_non_string_by_and_ts_to_none():
    """Stage-3 doubt review, finding 7: a forged/hand-edited line can carry a
    non-str `by`/`ts` (validation only checks the four AMENDABLE_FIELDS) —
    `apply_amend` must collapse it to None, keeping `amendedBy`/`amendedAt`
    `str | None` for every consumer, same as `mark_status`'s own `status`
    guard."""
    item = _base_item()
    raw = {"title": "x", "by": ["not", "a", "string"], "ts": 12345}
    triage_amend.apply_amend(item, raw, priority_from_severity=_priority)
    assert item[triage_amend.AMENDED_BY_FIELD] is None
    assert item[triage_amend.AMENDED_AT_FIELD] is None
