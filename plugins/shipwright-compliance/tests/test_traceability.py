"""Tests for the BP-1 dashboard traceability metrics.

count_traced (grade input) credits FR-linked AND satisfied-no-FR changes;
render_traced_row (dashboard) measures genuine FR-linkage and flags a freeze.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.lib._traceability import count_traced, render_traced_row


def _ev(source="iterate", affected_frs=None, new_frs=None, change_type="",
        none_reason="", spec_impact="", section=""):
    return SimpleNamespace(
        source=source,
        affected_frs=affected_frs or [],
        new_frs=new_frs or [],
        change_type=change_type,
        none_reason=none_reason,
        spec_impact=spec_impact,
        section=section,
    )


class TestCountTraced:
    def test_credits_fr_linked_and_satisfied_no_fr(self):
        events = [
            _ev(affected_frs=["FR-01.10"], spec_impact="modify"),       # FR-linked
            _ev(change_type="tooling", none_reason="CI", spec_impact="none"),  # sat no-FR
            _ev(change_type="compliance", none_reason="realign"),       # sat no-FR
        ]
        assert count_traced(events) == 3

    def test_excludes_unclassified_and_legacy(self):
        events = [
            _ev(),                                       # unclassified
            _ev(change_type="fix", none_reason="x"),     # legacy invalid change_type
            _ev(change_type="tooling", none_reason=""),  # missing reason
        ]
        assert count_traced(events) == 0

    def test_behavior_affecting_no_fr_not_traced(self):
        # A behavior change hiding behind change_type is NOT traced.
        events = [_ev(change_type="compliance", none_reason="x", spec_impact="modify")]
        assert count_traced(events) == 0

    def test_build_event_traced_via_section(self):
        events = [_ev(source="build", section="01-login")]
        assert count_traced(events) == 1


class TestRenderTracedRow:
    def test_flags_a_relative_drop(self):
        # 10 FR-tagged then 25 no-FR: recent window (30) holds 5 FR-tags at a
        # LOWER rate than all-time → WARN via the relative-drop branch.
        events = [_ev(affected_frs=["FR-01.01"]) for _ in range(10)]
        events += [_ev(change_type="tooling", none_reason="x", spec_impact="none")
                   for _ in range(25)]
        row = render_traced_row(events)
        assert "Recent changes traced to an FR" in row
        assert "WARN" in row
        assert "FR-tagging dropped" in row

    def test_flags_a_total_freeze(self):
        # 1 FR-tagged early, then 40 no-FR → recent window 0% → WARN (freeze).
        events = [_ev(affected_frs=["FR-01.01"])]
        events += [_ev(change_type="tooling", none_reason="x", spec_impact="none")
                   for _ in range(40)]
        row = render_traced_row(events)
        assert "WARN" in row
        assert "frozen" in row

    def test_no_drop_when_recent_meets_alltime(self):
        events = [_ev(affected_frs=["FR-01.01"]) for _ in range(10)]
        row = render_traced_row(events)
        assert "PASS" in row
        assert "100%" in row

    def test_no_iterate_events(self):
        row = render_traced_row([_ev(source="build", section="01-x")])
        assert "n/a" in row

    def test_measures_fr_linkage_not_classification(self):
        # All satisfied no-FR → FR-linkage is 0%, even though all are "traced".
        events = [_ev(change_type="tooling", none_reason="x", spec_impact="none")
                  for _ in range(10)]
        row = render_traced_row(events)
        assert "0/10 (0%)" in row

    def test_steady_state_freeze_warns_on_absolute_floor(self):
        # No FR tags ever (recent == all-time == 0%) must still WARN — a steady
        # freeze the relative drop test alone would miss.
        events = [_ev(change_type="tooling", none_reason="x", spec_impact="none")
                  for _ in range(10)]
        row = render_traced_row(events)
        assert "WARN" in row
        assert "frozen" in row
