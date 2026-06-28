"""Tests for BP-2: per-FR ``fr_impact`` reader + the reconciliation helper +
the Control-Grade adapter lighting the reconciliation dimension.

The reconciliation helper is the single SSOT shared by the grade adapter
(``_control_block.build_grade_inputs``) and — from cc3 — the RTM "Reconciled?"
column, so the two can never drift. Reconciliation keys on *touched-without-
re-verify*, never on age.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.lib._control_block import build_grade_inputs
from scripts.lib._reconciliation import compute_reconciliation
from scripts.lib.collectors._types import WorkEvent


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


# --------------------------------------------------------------------------
# Reader: WorkEvent.fr_impact
# --------------------------------------------------------------------------

class TestWorkEventFrImpact:
    def test_parses_fr_impact_map(self):
        we = WorkEvent.from_dict({
            "id": "evt-1", "ts": "2026-06-28T00:00:00+00:00",
            "type": "work_completed", "source": "iterate",
            "fr_impact": {"FR-01.07": "MODIFY", "FR-02.03": "none"},
        })
        assert we.fr_impact == {"FR-01.07": "modify", "FR-02.03": "none"}

    def test_legacy_event_has_empty_map(self):
        we = WorkEvent.from_dict({"id": "e", "ts": "t", "source": "iterate"})
        assert we.fr_impact == {}

    def test_null_fr_impact_coerces_to_empty(self):
        # An explicit null must coerce like a missing key (never crash readers).
        we = WorkEvent.from_dict({"id": "e", "source": "iterate", "fr_impact": None})
        assert we.fr_impact == {}

    def test_garbage_fr_impact_is_tolerated(self):
        # Non-dict, or non-str entries, are dropped — the reader never raises.
        we = WorkEvent.from_dict({"id": "e", "source": "iterate", "fr_impact": "modify"})
        assert we.fr_impact == {}
        we2 = WorkEvent.from_dict(
            {"id": "e", "source": "iterate", "fr_impact": {"FR-1": 9, "FR-2": "add"}})
        assert we2.fr_impact == {"FR-2": "add"}


# --------------------------------------------------------------------------
# Reconciliation helper
# --------------------------------------------------------------------------

class TestComputeReconciliation:
    def test_behavior_touch_without_test_is_unreconciled(self):
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00",
                affected=["FR-01.07"], fr_impact={"FR-01.07": "modify"},
                tests_total=0),
        ])
        assert rec.behavior_touched == {"FR-01.07"}
        assert rec.unreconciled == {"FR-01.07"}
        assert rec.status("FR-01.07") == "needs_reverification"

    def test_touch_and_test_in_same_event_is_reconciled(self):
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00",
                affected=["FR-01.07"], fr_impact={"FR-01.07": "modify"},
                tests_total=12),
        ])
        assert rec.behavior_touched == {"FR-01.07"}
        assert rec.unreconciled == set()
        assert rec.status("FR-01.07") == "reconciled"

    def test_later_tested_event_reconciles_an_earlier_touch(self):
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00",
                affected=["FR-01.07"], fr_impact={"FR-01.07": "modify"}, tests_total=0),
            _we("2026-06-05T00:00:00+00:00", affected=["FR-01.07"], tests_total=8),
        ])
        assert rec.status("FR-01.07") == "reconciled"

    def test_touch_after_last_test_is_unreconciled(self):
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00", affected=["FR-01.07"], tests_total=8),
            _we("2026-06-05T00:00:00+00:00",
                affected=["FR-01.07"], fr_impact={"FR-01.07": "modify"}, tests_total=0),
        ])
        assert rec.status("FR-01.07") == "needs_reverification"

    def test_age_alone_never_flags(self):
        # A very old behavior touch that WAS verified stays reconciled forever.
        rec = compute_reconciliation([
            _we("2020-01-01T00:00:00+00:00",
                affected=["FR-09.01"], fr_impact={"FR-09.01": "modify"}, tests_total=3),
        ])
        assert rec.unreconciled == set()
        assert rec.status("FR-09.01") == "reconciled"

    def test_event_level_spec_impact_fallback_for_legacy_events(self):
        # No fr_impact map → fall back to event-level spec_impact over affected_frs.
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00",
                affected=["FR-03.01", "FR-03.02"], spec_impact="modify", tests_total=0),
        ])
        assert rec.behavior_touched == {"FR-03.01", "FR-03.02"}
        assert rec.unreconciled == {"FR-03.01", "FR-03.02"}

    def test_doc_only_touch_never_behavior_affecting(self):
        # spec_impact none + no fr_impact behavior entries → zero touched.
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00",
                affected=["FR-04.01"], spec_impact="none", tests_total=0),
            _we("2026-06-02T00:00:00+00:00",
                affected=["FR-04.02"], fr_impact={"FR-04.02": "none"}, tests_total=0),
        ])
        assert rec.behavior_touched == set()
        assert rec.unreconciled == set()

    def test_per_fr_granularity(self):
        # One event: FR-A behavior-modified (untested → unreconciled), FR-B none.
        rec = compute_reconciliation([
            _we("2026-06-01T00:00:00+00:00",
                affected=["FR-A", "FR-B"],
                fr_impact={"FR-A": "modify", "FR-B": "none"}, tests_total=0),
        ])
        assert rec.behavior_touched == {"FR-A"}
        assert rec.status("FR-A") == "needs_reverification"
        assert rec.status("FR-B") == "untouched"

    def test_untouched_fr_status(self):
        rec = compute_reconciliation([])
        assert rec.status("FR-99.99") == "untouched"

    def test_malformed_timestamp_is_skipped(self):
        rec = compute_reconciliation([
            _we("not-a-date", affected=["FR-1"], fr_impact={"FR-1": "modify"}),
        ])
        assert rec.behavior_touched == set()


# --------------------------------------------------------------------------
# Grade adapter — light the reconciliation dimension
# --------------------------------------------------------------------------

def _req(fr_id):
    return SimpleNamespace(id=fr_id, sections=[])


def _wev(ts, *, affected=None, fr_impact=None, tests_total=0):
    """A real WorkEvent (the adapter calls count_traced / latest-suite, which
    need the full field surface — a minimal SimpleNamespace won't do)."""
    return WorkEvent(
        id="evt-x", timestamp=ts, source="iterate",
        tests_passed=tests_total, tests_total=tests_total,
        affected_frs=affected or [], fr_impact=fr_impact or {},
    )


def _data(work_events, requirements):
    return SimpleNamespace(
        work_events=work_events,
        requirements=requirements,
        dependencies=[],
        project_root=None,
    )


class TestBuildGradeInputsReconciliation:
    def test_reconciliation_now_measurable(self):
        data = _data(
            [_wev("2026-06-01T00:00:00+00:00",
                  affected=["FR-1"], fr_impact={"FR-1": "modify"}, tests_total=5)],
            [_req("FR-1")],
        )
        inp = build_grade_inputs(data)
        assert inp.reconciliation_measurable is True

    def test_no_requirements_is_not_measurable(self):
        # Events but zero declared requirements → n/a (no free 1.0).
        data = _data(
            [_wev("2026-06-01T00:00:00+00:00",
                  affected=["FR-1"], fr_impact={"FR-1": "modify"}, tests_total=5)],
            [],
        )
        inp = build_grade_inputs(data)
        assert inp.reconciliation_measurable is False

    def test_no_behavior_touches_is_not_measurable(self):
        # Requirements + events but no behavior-affecting touch → n/a, not a
        # vacuous 1.0: nothing to reconcile means nothing to measure.
        data = _data(
            [_wev("2026-06-01T00:00:00+00:00", affected=["FR-1"], tests_total=5)],
            [_req("FR-1")],
        )
        inp = build_grade_inputs(data)
        assert inp.reconciliation_measurable is False

    def test_counts_filtered_to_declared_requirements(self):
        # FR-2 is touched-unreconciled but NOT a declared requirement → excluded
        # so the grade and the RTM (which iterates requirements) agree.
        data = _data(
            [
                _wev("2026-06-01T00:00:00+00:00",
                     affected=["FR-1"], fr_impact={"FR-1": "modify"}, tests_total=0),
                _wev("2026-06-02T00:00:00+00:00",
                     affected=["FR-2"], fr_impact={"FR-2": "modify"}, tests_total=0),
            ],
            [_req("FR-1")],
        )
        inp = build_grade_inputs(data)
        assert inp.frs_behavior_touched == 1
        assert inp.frs_unreconciled == 1

    def test_agrees_with_helper(self):
        events = [
            _wev("2026-06-01T00:00:00+00:00",
                 affected=["FR-1"], fr_impact={"FR-1": "modify"}, tests_total=9),
            _wev("2026-06-02T00:00:00+00:00",
                 affected=["FR-2"], fr_impact={"FR-2": "modify"}, tests_total=0),
        ]
        reqs = [_req("FR-1"), _req("FR-2")]
        rec = compute_reconciliation(events)
        inp = build_grade_inputs(_data(events, reqs))
        req_ids = {r.id for r in reqs}
        assert inp.frs_behavior_touched == len(rec.behavior_touched & req_ids)
        assert inp.frs_unreconciled == len(rec.unreconciled & req_ids)
