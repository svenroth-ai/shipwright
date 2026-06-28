"""Tests for the shared FR-classification SSOT (BP-1).

Pins the "traced = FR-linked OR satisfied no-FR" predicate and the discriminating
"satisfied no-FR" definition (valid change_type + valid none_reason +
behavior-preserving). Drift-protection: the constants here MUST match the
record_event FR-gate's, so an event that passes the gate as no-FR is always
counted as traced.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib import fr_classification as fc  # noqa: E402


class TestIsBehaviorAffecting:
    def test_add_modify_remove_are_behavior_affecting(self):
        for v in ("add", "modify", "remove", "MODIFY", " Add "):
            assert fc.is_behavior_affecting(v) is True, v

    def test_none_and_empty_are_preserving(self):
        for v in ("none", "NONE", "", None, "   "):
            assert fc.is_behavior_affecting(v) is False, v


class TestIsFrTagged:
    def test_affected_or_new(self):
        assert fc.is_fr_tagged(["FR-01.01"], []) is True
        assert fc.is_fr_tagged([], ["FR-02.07"]) is True

    def test_empty_and_malformed(self):
        assert fc.is_fr_tagged([], []) is False
        assert fc.is_fr_tagged(["", "  "], None) is False
        assert fc.is_fr_tagged(("FR-01.01",), None) is False  # tuple, not list


class TestIsSatisfiedNoFr:
    def test_valid_preserving_change_is_satisfied(self):
        assert fc.is_satisfied_no_fr("tooling", "CI fix", "none") is True
        assert fc.is_satisfied_no_fr("compliance", "audit realign", None) is True

    def test_behavior_affecting_is_never_satisfied(self):
        # The discriminator: a behavior change can't hide behind change_type.
        assert fc.is_satisfied_no_fr("tooling", "CI fix", "modify") is False

    def test_invalid_change_type_not_satisfied(self):
        assert fc.is_satisfied_no_fr("fix", "legacy", "none") is False
        assert fc.is_satisfied_no_fr("chore", "legacy", "none") is False
        assert fc.is_satisfied_no_fr(None, "reason", "none") is False

    def test_invalid_none_reason_not_satisfied(self):
        assert fc.is_satisfied_no_fr("tooling", "", "none") is False
        assert fc.is_satisfied_no_fr("tooling", "multi\nline", "none") is False
        assert fc.is_satisfied_no_fr("tooling", "x" * 281, "none") is False


class TestIsTraced:
    def test_fr_linked_is_traced(self):
        assert fc.is_traced(["FR-01.10"], [], None, None, "modify") is True

    def test_satisfied_no_fr_is_traced(self):
        assert fc.is_traced([], [], "tooling", "CI fix", "none") is True

    def test_unclassified_is_not_traced(self):
        assert fc.is_traced([], [], None, None, "none") is False

    def test_behavior_affecting_without_fr_is_not_traced(self):
        # Even with a valid change_type+reason, a behavior change w/o an FR
        # is NOT traced — mirrors the gate rejecting it.
        assert fc.is_traced([], [], "compliance", "realign", "modify") is False


class TestNormalizeFrImpact:
    """BP-2: the per-FR impact map validator (producer-side SSOT)."""

    def test_none_and_empty_yield_empty(self):
        assert fc.normalize_fr_impact(None) == {}
        assert fc.normalize_fr_impact({}) == {}

    def test_valid_map_lowercased_and_trimmed(self):
        out = fc.normalize_fr_impact({"FR-01.07": "MODIFY", " FR-02.03 ": "none"})
        assert out == {"FR-01.07": "modify", "FR-02.03": "none"}

    def test_all_impact_values_accepted(self):
        out = fc.normalize_fr_impact(
            {"FR-1": "add", "FR-2": "modify", "FR-3": "remove", "FR-4": "none"})
        assert out == {"FR-1": "add", "FR-2": "modify", "FR-3": "remove", "FR-4": "none"}

    def test_non_dict_rejected(self):
        for bad in ("modify", ["FR-01.07"], 7):
            try:
                fc.normalize_fr_impact(bad)
            except ValueError:
                continue
            raise AssertionError(f"expected ValueError for {bad!r}")

    def test_invalid_impact_value_rejected(self):
        try:
            fc.normalize_fr_impact({"FR-01.07": "tweak"})
        except ValueError:
            return
        raise AssertionError("expected ValueError for unknown impact")

    def test_blank_key_rejected(self):
        try:
            fc.normalize_fr_impact({"  ": "modify"})
        except ValueError:
            return
        raise AssertionError("expected ValueError for blank FR id")

    def test_non_string_impact_rejected(self):
        try:
            fc.normalize_fr_impact({"FR-01.07": 1})
        except ValueError:
            return
        raise AssertionError("expected ValueError for non-string impact")

    def test_spec_impact_values_superset_of_behavior_affecting(self):
        # The fr_impact vocab MUST include every behavior-affecting value plus
        # 'none' — drift here would let a valid spec_impact be an invalid
        # fr_impact value.
        assert set(fc.BEHAVIOR_AFFECTING) <= set(fc.SPEC_IMPACT_VALUES)
        assert "none" in fc.SPEC_IMPACT_VALUES


class TestDriftWithGate:
    """The compliance 'traced' notion must not drift from the record_event gate."""

    def test_constants_match_record_event_gate(self):
        tools = Path(__file__).resolve().parents[1] / "scripts" / "tools"
        sys.path.insert(0, str(tools))
        import record_event as re_mod

        assert re_mod._CHANGE_TYPE_VALUES == fc.CHANGE_TYPE_VALUES
        assert re_mod._NONE_REASON_MAX_LEN == fc.NONE_REASON_MAX_LEN

    def test_satisfied_no_fr_implies_gate_passes(self):
        """Any event the predicate calls a satisfied no-FR change must PASS the
        gate's no-FR branch — the two definitions agree by construction."""
        tools = Path(__file__).resolve().parents[1] / "scripts" / "tools"
        sys.path.insert(0, str(tools))
        from record_event import _fr_or_change_type_gate_error

        event = {
            "type": "work_completed", "source": "iterate", "intent": "change",
            "change_type": "tooling", "none_reason": "CI fix", "spec_impact": "none",
        }
        assert fc.is_satisfied_no_fr("tooling", "CI fix", "none") is True
        assert _fr_or_change_type_gate_error(event) is None
