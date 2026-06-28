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
