"""iterate-2026-08-16-fr-gate-test-evidence: shape-fidelity regression for
this run's own reconciliation mechanics — a `spec_impact: none` event with a
non-empty `affected_frs` REFERENCES those FRs (re-verifying them, per
`_referenced_and_touched`'s `referenced` set) WITHOUT marking them
behavior-touched, so it can carry real `tests_total` and reconcile an earlier
untested touch without falsely claiming to have changed the FR's behavior.

Kept in its own file (not appended to `test_reconciliation.py`) per the
existing repo convention of splitting a cohesive new test cluster into a
sibling file rather than growing an established one past the 300-line
guideline.

Deliberately synthetic (not read from the live `shipwright_events.jsonl` —
that file changes with every merge, so a test pinned to its current content
would be a moving target, not a regression test). The mechanism under test —
"reference + any tests_total > 0 = reconciled" — is coarse by design:
`compute_reconciliation` does not verify the referenced tests actually
exercise that FR's behavior. That coarseness is pre-existing and out of this
card's scope; this test pins the MECHANISM's documented contract, not a claim
that the mechanism is unimprovable.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.lib._reconciliation import compute_reconciliation


def _we(ts, *, affected=None, new=None, spec_impact="", fr_impact=None,
        tests_total=0, source="iterate"):
    return SimpleNamespace(
        source=source,
        timestamp=ts,
        affected_frs=affected or [],
        new_frs=new or [],
        spec_impact=spec_impact,
        fr_impact=fr_impact or {},
        tests_total=tests_total,
    )


class TestCard20260816Reconciliation:
    def test_reconciling_event_closes_an_earlier_untested_touch(self):
        rec = compute_reconciliation([
            _we("2026-07-26T00:00:00+00:00",
                affected=["FR-01.01", "FR-01.10"], spec_impact="modify",
                tests_total=0),
            _we("2026-08-16T00:00:00+00:00",
                affected=["FR-01.01", "FR-01.10"], spec_impact="none",
                tests_total=9000),
        ])
        assert rec.status("FR-01.01") == "reconciled"
        assert rec.status("FR-01.10") == "reconciled"

    def test_out_of_scope_frs_stay_unreconciled_when_not_referenced(self):
        """FR-01.16/18/19-shaped rows — untested-touched and NOT named in the
        reconciling event — must still read needs_reverification afterward."""
        rec = compute_reconciliation([
            _we("2026-07-26T00:00:00+00:00",
                affected=["FR-01.01", "FR-01.16"], spec_impact="modify",
                tests_total=0),
            _we("2026-08-16T00:00:00+00:00",
                affected=["FR-01.01"], spec_impact="none", tests_total=9000),
        ])
        assert rec.status("FR-01.01") == "reconciled"
        assert rec.status("FR-01.16") == "needs_reverification"

    def test_reconciling_event_never_marks_referenced_frs_behavior_touched(self):
        """The whole trick: spec_impact=none must not itself add the
        referenced FRs to `behavior_touched` — only the earlier modify event
        does. A bug that made the reconciling event ALSO count as a touch
        would be self-cancelling (same event both breaks and fixes it)."""
        rec = compute_reconciliation([
            _we("2026-08-16T00:00:00+00:00",
                affected=["FR-02.01"], spec_impact="none", tests_total=9000),
        ])
        assert rec.behavior_touched == set()
        assert rec.status("FR-02.01") == "untouched"
