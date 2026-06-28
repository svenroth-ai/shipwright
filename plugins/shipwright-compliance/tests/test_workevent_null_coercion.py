"""Regression: ``WorkEvent.from_dict`` must coerce an EXPLICIT ``null`` to the
empty default, not just a MISSING key.

Bug (iterate-2026-06-12-workevent-null-frs-coerce): ``d.get("affected_frs",
[])`` returns ``None`` when the key is present with an explicit ``null`` value —
the default only fires when the key is ABSENT. A ``work_completed`` event
carrying ``"affected_frs": null`` (e.g. ``finalize_iterate --event-extras-json``
passing an explicit null instead of omitting the key) therefore yielded
``affected_frs=None``; downstream ``map_requirements_to_events`` then did
``for fr_id in we.affected_frs`` → ``TypeError: 'NoneType' object is not
iterable``, crashing the entire compliance markdown regen (dashboard / RTM /
SBOM / test-evidence / change-history). The fix mirrors the existing
``TestRunEvent.from_dict`` ``layers = d.get("layers") or {}`` guard (Gemini-L4):
coerce null + missing alike via ``or []`` (lists) / ``or {}`` (nested dicts) so
no producer that emits null can brick compliance.

Lives in its own file (not appended to the already-baseline-capped
``test_data_collector.py``) to keep that oversize file from ratcheting.
"""

from __future__ import annotations

from scripts.lib.data_collector import (
    RequirementInfo,
    WorkEvent,
    map_requirements_to_events,
)


class TestWorkEventNullCoercion:
    def _evt(self, **overrides: object) -> dict:
        base = {
            "id": "evt-null", "type": "work_completed", "source": "iterate",
            "ts": "2026-06-12T00:00:00Z", "commit": "abc123",
        }
        base.update(overrides)
        return base

    def test_explicit_null_affected_frs_coerces_to_empty_list(self):
        we = WorkEvent.from_dict(self._evt(affected_frs=None))
        assert we.affected_frs == []

    def test_explicit_null_new_frs_coerces_to_empty_list(self):
        we = WorkEvent.from_dict(self._evt(new_frs=None))
        assert we.new_frs == []

    def test_missing_keys_still_default_to_empty_list(self):
        # Regression guard: the normal omit-the-key path must keep working.
        we = WorkEvent.from_dict(self._evt())
        assert we.affected_frs == []
        assert we.new_frs == []

    def test_explicit_null_nested_dicts_do_not_crash(self):
        # `tests`/`review` are read with `.get(...)`; an explicit null there
        # must collapse to {} (same class of bug as the list fields).
        we = WorkEvent.from_dict(self._evt(tests=None, review=None))
        assert we.tests_passed == 0
        assert we.tests_total == 0
        assert we.review_findings == 0

    def test_populated_values_round_trip_unchanged(self):
        we = WorkEvent.from_dict(self._evt(
            affected_frs=["FR-01.01", "FR-02.03"],
            new_frs=["FR-09.09"],
            tests={"passed": 3, "total": 4},
        ))
        assert we.affected_frs == ["FR-01.01", "FR-02.03"]
        assert we.new_frs == ["FR-09.09"]
        assert we.tests_passed == 3
        assert we.tests_total == 4

    def test_bp1_classification_fields_round_trip(self):
        # BP-1: change_type / none_reason / spec_impact must survive from_dict
        # (the producer→reader boundary the traced-% metric + grade depend on).
        we = WorkEvent.from_dict(self._evt(
            change_type="compliance", none_reason="audit realign",
            spec_impact="none",
        ))
        assert we.change_type == "compliance"
        assert we.none_reason == "audit realign"
        assert we.spec_impact == "none"

    def test_bp1_fields_tolerant_of_legacy_and_null(self):
        # Legacy events (fields absent) and explicit-null both coerce to "".
        legacy = WorkEvent.from_dict(self._evt())
        assert (legacy.change_type, legacy.none_reason, legacy.spec_impact) == ("", "", "")
        nulled = WorkEvent.from_dict(self._evt(
            change_type=None, none_reason=None, spec_impact=None))
        assert (nulled.change_type, nulled.none_reason, nulled.spec_impact) == ("", "", "")

    def test_null_affected_frs_does_not_brick_rtm_mapping(self):
        # The actual reported failure mode: the whole compliance regen crashed
        # because map_requirements_to_events iterated a None affected_frs.
        we = WorkEvent.from_dict(self._evt(affected_frs=None, new_frs=None))
        reqs = [
            RequirementInfo(id="FR-01.01", text="x", priority="Must", split="01"),
        ]
        # Must NOT raise TypeError: 'NoneType' object is not iterable.
        map_requirements_to_events(reqs, [we])
        # Null event contributes no mappings; the requirement stays unmapped.
        assert reqs[0].sections == []
