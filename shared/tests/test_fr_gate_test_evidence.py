"""iterate-2026-08-16-fr-gate-test-evidence: a behaviour-affecting, FR-declaring
work_completed event must carry test evidence OR state why it cannot.

Mirrors test_fr_gate_behavior_affecting.py's shape: 48 of 119 recorded events
declared FRs with no `tests.total` at all — `record_event.build_event` builds
the `tests` block purely from CLI args, so a caller that passes none gets no
block and nothing objects. This closes it the same way BP-1 closed the no-FR
case: `change_type`+`none_reason` for "this touches no FR", `no_tests_reason`
for "this touches FR(s) but I can't prove it with tests right now".

Lives in its own file (not appended to the baseline-capped
test_record_event.py) to avoid ratcheting it, per the existing convention.
"""

from __future__ import annotations

from lib.fr_gates import run_fr_gates
# Short local alias, purely for call-site brevity in this file.
from lib.fr_test_evidence_gate import missing_test_evidence_error as gate_error


def _iterate_event(**overrides) -> dict:
    event = {"type": "work_completed", "source": "iterate", "intent": "change"}
    event.update(overrides)
    return event


class TestTestEvidenceGate:
    def test_behavior_affecting_with_frs_no_tests_no_reason_blocked(self):
        """The literal silent case: spec_impact behaviour-affecting, FRs
        declared, no tests block, no no_tests_reason."""
        event = _iterate_event(spec_impact="modify", affected_frs=["FR-01.10"])
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_behavior_affecting_with_new_frs_no_tests_no_reason_blocked(self):
        event = _iterate_event(spec_impact="add", new_frs=["FR-02.07"])
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_behavior_affecting_with_no_tests_reason_passes(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            no_tests_reason="scanner change — no isolated test harness yet",
        )
        assert gate_error(event) is None

    def test_behavior_affecting_with_tests_block_passes(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            tests={"passed": 5, "total": 5},
        )
        assert gate_error(event) is None

    def test_behavior_affecting_with_zero_total_tests_block_requires_reason(self):
        # tests.total present but 0 is not evidence of anything having run —
        # matches every read-side consumer (compute_reconciliation,
        # derive_tests_block's own "zero tests is not evidence" refusal).
        # A caller with zero selected tests still owes a no_tests_reason.
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            tests={"passed": 0, "total": 0},
        )
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_behavior_affecting_with_negative_total_requires_reason(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            tests={"passed": 0, "total": -1},
        )
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_bool_total_is_not_evidence(self):
        # `total: True` is reachable via caller-supplied event_extras JSON
        # (`true` is a legal JSON value); bool is a subclass of int in Python,
        # so a naive `isinstance(total, int)` check alone would misread it as
        # `total > 0` evidence. Guards the isinstance(total, bool) exclusion.
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"], tests={"total": True},
        )
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_behavior_preserving_bypasses_gate(self):
        # spec_impact none (or absent) — docs-only / behaviour-preserving
        # iterate must never be gated by this rule even with FRs and no tests,
        # as long as it only REFERENCES an existing FR (affected_frs).
        event = _iterate_event(spec_impact="none", affected_frs=["FR-01.10"])
        assert gate_error(event) is None

    def test_minted_fr_is_gated_even_with_spec_impact_none(self):
        # doubt-review D3-1: new_frs MINTS a requirement — that is always an
        # "add", so spec_impact: none alongside it must not bypass the gate
        # (self-contradictory: "no behaviour change" + "brand-new FR").
        event = _iterate_event(spec_impact="none", new_frs=["FR-02.07"])
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_minted_fr_with_no_tests_reason_passes_even_with_spec_impact_none(self):
        event = _iterate_event(
            spec_impact="none", new_frs=["FR-02.07"],
            no_tests_reason="minted from an adopt scan, verified by hand",
        )
        assert gate_error(event) is None

    def test_missing_spec_impact_bypasses_gate(self):
        event = _iterate_event(affected_frs=["FR-01.10"])
        assert gate_error(event) is None

    def test_no_frs_bypasses_this_gate(self):
        # No FRs declared at all — the existing classification gate
        # (fr_or_change_type_gate_error) owns rejecting this case, not this one.
        event = _iterate_event(spec_impact="modify")
        assert gate_error(event) is None

    def test_build_events_bypass_gate(self):
        event = {
            "type": "work_completed", "source": "build",
            "spec_impact": "modify", "affected_frs": ["FR-01.10"],
        }
        assert gate_error(event) is None

    def test_non_work_completed_events_bypass(self):
        for etype in ("task_created", "phase_started", "phase_completed"):
            event = {"type": etype, "source": "iterate", "spec_impact": "modify"}
            assert gate_error(event) is None

    def test_malformed_dict_input_clean_bypass(self):
        assert gate_error({}) is None
        assert gate_error("not-a-dict") is None
        assert gate_error(None) is None

    def test_non_dict_tests_field_treated_as_no_evidence(self):
        # A corrupt/legacy `tests` value that isn't a dict must not be read
        # as evidence — falls through to requiring no_tests_reason.
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"], tests="not-a-dict",
        )
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_tests_block_without_total_key_requires_reason(self):
        # A tests dict present but missing 'total' (e.g. only 'passed' set)
        # is not evidence of a total — still requires no_tests_reason.
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            tests={"passed": 5},
        )
        err = gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"


class TestNoTestsReasonValidation:
    def test_blank_reason_rejected(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"], no_tests_reason="   ",
        )
        err = gate_error(event)
        assert err is not None

    def test_oversized_reason_rejected(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            no_tests_reason="x" * 300,
        )
        err = gate_error(event)
        assert err is not None

    def test_control_chars_in_reason_rejected(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            no_tests_reason="no tests\x1byet",
        )
        err = gate_error(event)
        assert err is not None

    def test_tab_in_reason_allowed(self):
        event = _iterate_event(
            spec_impact="modify", affected_frs=["FR-01.10"],
            no_tests_reason="no tests\tyet",
        )
        assert gate_error(event) is None


class TestRunFrGatesOrdering:
    """The new gate sits inside run_fr_gates, AFTER classification and
    existence (doubt-review, iterate-2026-08-16-fr-gate-test-evidence:
    identity is logically prior to evidence — there cannot be test evidence
    for a requirement that does not exist). An unclassified event still
    surfaces the classification error first. Uses `tmp_path` (never the live
    repo cwd) so the existence gate degrades to unverifiable/allow
    deterministically — no accidental coupling to whichever real FR ids
    happen to exist in .shipwright/planning/. The existence-before-evidence
    precedence itself (a classified, unevidenced event naming an UNKNOWN FR
    against a real spec) is pinned in
    test_fr_gate_existence.py::TestWiringActuallyEnforces, which already owns
    the `_make_project` fixture this needs."""

    def test_unclassified_and_no_tests_surfaces_classification_error_first(self, tmp_path):
        event = _iterate_event(spec_impact="modify")  # no FRs, no change_type
        err = run_fr_gates(event, project_root=tmp_path, caller="test")
        assert err is not None
        assert err["error"] == "fr_gate_behavior_affecting_requires_fr"

    def test_classified_but_no_tests_surfaces_test_evidence_error(self, tmp_path):
        event = _iterate_event(spec_impact="modify", affected_frs=["FR-01.10"])
        err = run_fr_gates(event, project_root=tmp_path, caller="test")
        assert err is not None
        assert err["error"] == "fr_gate_missing_test_evidence"

    def test_classified_with_tests_passes_run_fr_gates(self, tmp_path):
        # No .shipwright/planning under tmp_path — existence gate degrades to
        # unverifiable/allow, so a fully-satisfied event passes cleanly.
        event = _iterate_event(
            spec_impact="none", affected_frs=["FR-01.10"],
            tests={"passed": 1, "total": 1},
        )
        assert run_fr_gates(event, project_root=tmp_path, caller="test") is None
