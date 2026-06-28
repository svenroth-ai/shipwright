"""cc3 (AR-05): RTM "Reconciled?" column + readability, consuming BP-2.

These pin the six AR-05 behaviors, kept in a separate file because
``test_rtm_generator.py`` is already a frozen anti-ratchet baseline entry:

1. ``Reconciled?`` column keyed on the BP-2 reconciliation helper
   (✅ / ⚠️ needs re-verification / —);
2. age-alone NEVER flags (touched-and-tested-in-2020 stays ✅);
3. ``Last Verified`` renamed to neutral ``Last tested``;
4. full FR titles (no 60-char truncation);
5. ``evt-`` evidence links to the Verification Timeline anchor;
6. a legend decodes the Tests / Last tested / Reconciled? columns.

The grade-agreement test proves the column and the Control-Grade
reconciliation dimension read the SAME ``_reconciliation`` helper, so they
can never disagree.
"""

from __future__ import annotations

from pathlib import Path

from scripts.lib._reconciliation import compute_reconciliation
from scripts.lib.data_collector import ComplianceData, RequirementInfo, WorkEvent
from scripts.lib.rtm_generator import generate


def _data(tmp_path: Path, events, requirements=None) -> ComplianceData:
    data = ComplianceData(project_root=tmp_path, timestamp="2026-06-28T00:00:00Z")
    data.requirements = requirements or [
        RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
    ]
    data.work_events = events
    return data


def _row(result: str, fr_id: str = "FR-01.01") -> str:
    rows = [l for l in result.splitlines() if l.startswith(f"| [{fr_id}]")]
    assert rows, f"{fr_id} coverage row missing"
    return rows[0]


def _cell(row: str, idx: int) -> str:
    """1=Requirement 2=Title 3=Priority 4=Verified By 5=Tests 6=Last tested
    7=Reconciled? 8=Status (leading '|' makes index 0 the empty prefix)."""
    return row.split("|")[idx].strip()


def _ev(eid, ts, *, frs=("FR-01.01",), passed=0, total=0, fr_impact=None, desc="work"):
    return WorkEvent(
        id=eid, timestamp=ts, source="iterate", description=desc,
        tests_passed=passed, tests_total=total,
        affected_frs=list(frs), fr_impact=fr_impact or {},
    )


# ---------------------------------------------------------------------------
# Reconciled? column
# ---------------------------------------------------------------------------

class TestReconciledColumn:
    def test_header_renamed_and_column_added(self, tmp_path: Path):
        result = generate(_data(tmp_path, [_ev("evt-00000001", "2026-06-01T00:00:00Z",
                                                passed=5, total=5)]))
        assert "Reconciled?" in result
        assert "Last tested" in result
        assert "Last Verified" not in result

    def test_behavior_touch_reverified_is_check(self, tmp_path: Path):
        # touched + tested in the same event → reconciled.
        result = generate(_data(tmp_path, [
            _ev("evt-aaaa1111", "2026-06-01T00:00:00Z", passed=5, total=5,
                fr_impact={"FR-01.01": "modify"}),
        ]))
        assert _cell(_row(result), 7) == "✅"

    def test_behavior_touch_unverified_needs_reverification(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("evt-bbbb2222", "2026-06-01T00:00:00Z", passed=0, total=0,
                fr_impact={"FR-01.01": "modify"}),
        ]))
        assert _cell(_row(result), 7) == "⚠️ needs re-verification"

    def test_not_behavior_touched_is_dash(self, tmp_path: Path):
        # FR referenced by a tested event but no behavior impact → untouched.
        result = generate(_data(tmp_path, [
            _ev("evt-cccc3333", "2026-06-01T00:00:00Z", passed=5, total=5),
        ]))
        assert _cell(_row(result), 7) == "—"

    def test_age_alone_never_flags(self, tmp_path: Path):
        # A 2020 behavior change that WAS re-verified stays ✅ forever, and is
        # absent from the "needs re-verification" subsection. (AR-05 AC-1.)
        result = generate(_data(tmp_path, [
            _ev("evt-dddd4444", "2020-01-01T00:00:00Z", passed=3, total=3,
                fr_impact={"FR-01.01": "modify"}),
        ]))
        assert _cell(_row(result), 7) == "✅"
        assert "### FRs needing re-verification" not in result

    def test_later_test_reconciles_earlier_touch(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("evt-eeee5555", "2026-06-01T00:00:00Z", passed=0, total=0,
                fr_impact={"FR-01.01": "modify"}),
            _ev("evt-ffff6666", "2026-06-05T00:00:00Z", passed=8, total=8),
        ]))
        assert _cell(_row(result), 7) == "✅"


# ---------------------------------------------------------------------------
# Grade ↔ RTM agreement (single shared helper)
# ---------------------------------------------------------------------------

class TestColumnAgreesWithHelper:
    def test_per_fr_status_matches_compute_reconciliation(self, tmp_path: Path):
        events = [
            _ev("evt-11110000", "2026-06-01T00:00:00Z", frs=["FR-01.01"], passed=9, total=9,
                fr_impact={"FR-01.01": "modify"}),                       # reconciled
            _ev("evt-22220000", "2026-06-02T00:00:00Z", frs=["FR-01.02"], passed=0, total=0,
                fr_impact={"FR-01.02": "modify"}),                       # needs re-verify
            _ev("evt-33330000", "2026-06-03T00:00:00Z", frs=["FR-01.03"], passed=4, total=4),  # untouched
        ]
        reqs = [
            RequirementInfo(id="FR-01.01", text="A", priority="Must", split="01-x"),
            RequirementInfo(id="FR-01.02", text="B", priority="Must", split="01-x"),
            RequirementInfo(id="FR-01.03", text="C", priority="Must", split="01-x"),
        ]
        rec = compute_reconciliation(events)
        result = generate(_data(tmp_path, events, requirements=reqs))
        mark = {"reconciled": "✅", "needs_reverification": "⚠️ needs re-verification",
                "untouched": "—"}
        for req in reqs:
            assert _cell(_row(result, req.id), 7) == mark[rec.status(req.id)]


# ---------------------------------------------------------------------------
# Needs-re-verification subsection (replaces age-based "stale")
# ---------------------------------------------------------------------------

class TestNeedsReverificationSection:
    def test_unreconciled_fr_listed(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("evt-77770000", "2026-06-01T00:00:00Z", passed=0, total=0,
                fr_impact={"FR-01.01": "modify"}),
        ]))
        assert "### FRs needing re-verification" in result
        block = result.split("### FRs needing re-verification")[1].split("###")[0]
        assert "FR-01.01" in block

    def test_reconciled_fr_not_listed(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("evt-88880000", "2026-06-01T00:00:00Z", passed=5, total=5,
                fr_impact={"FR-01.01": "modify"}),
        ]))
        assert "### FRs needing re-verification" not in result

    def test_no_age_based_stale_section_anywhere(self, tmp_path: Path):
        # The old age-based clause is gone for good.
        result = generate(_data(tmp_path, [
            _ev("evt-99990000", "2020-01-01T00:00:00Z", passed=5, total=5),
        ]))
        assert "stale verification" not in result


# ---------------------------------------------------------------------------
# Readability: full titles, clickable evt-, legend
# ---------------------------------------------------------------------------

class TestReadability:
    def test_full_fr_title_not_truncated(self, tmp_path: Path):
        long_text = (
            "The system SHALL render a reconciliation column whose requirement "
            "title is comfortably longer than the old sixty-character cap"
        )
        result = generate(_data(
            tmp_path,
            [_ev("evt-aabb0011", "2026-06-01T00:00:00Z", passed=5, total=5)],
            requirements=[RequirementInfo(id="FR-01.01", text=long_text,
                                          priority="Must", split="01-auth")],
        ))
        assert long_text in result
        assert "..." not in _row(result)

    def test_evt_id_links_to_timeline_anchor(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("evt-12345678", "2026-06-01T00:00:00Z", passed=5, total=5, desc="do work"),
        ]))
        assert "[evt-12345678](#evt-12345678)" in _row(result)
        assert '<a id="evt-12345678">' in result  # matching timeline anchor

    def test_malformed_evt_id_not_linked(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("ev-1", "2026-06-01T00:00:00Z", passed=5, total=5),
        ]))
        row = _row(result)
        assert "[ev-1](#ev-1)" not in row
        assert "ev-1" in row  # still shown, just as plain text

    def test_legend_decodes_columns(self, tmp_path: Path):
        result = generate(_data(tmp_path, [
            _ev("evt-cafe0001", "2026-06-01T00:00:00Z", passed=5, total=5),
        ]))
        assert "**Legend**" in result
        assert "passed/total" in result
        assert "not a penalty" in result          # Last tested is age-neutral
        assert "not behavior-touched" in result   # the — Reconciled? state


class TestReconciledMarkNoDrift:
    """The Reconciled? glyph map uses literal keys (to keep the lazy-import
    contract); a meta-test pins them to the helper's status constants so they
    can never drift apart."""

    def test_keys_match_reconciliation_constants(self):
        from scripts.lib import _reconciliation as r
        from scripts.lib._rtm_reconciliation_render import _RECONCILED_MARK

        assert set(_RECONCILED_MARK) == {
            r.RECONCILED, r.NEEDS_REVERIFICATION, r.UNTOUCHED,
        }


class TestNullReconciliationFallback:
    """In a minimal env where the BP-2 helper can't be imported, the column
    degrades to ``—`` (untouched) instead of crashing the whole RTM render."""

    def test_null_reconciliation_reads_untouched(self):
        from scripts.lib._rtm_reconciliation_render import _NullReconciliation

        null = _NullReconciliation()
        assert null.status("FR-01.01") == "untouched"
        assert null.unreconciled == set()

    def test_safe_wrapper_returns_usable_object(self):
        # Normal input yields a real Reconciliation with the expected status.
        from scripts.lib._rtm_reconciliation_render import _compute_reconciliation_safe

        rec = _compute_reconciliation_safe([
            _ev("evt-feed0001", "2026-06-01T00:00:00Z", passed=0, total=0,
                fr_impact={"FR-01.01": "modify"}),
        ])
        assert rec.status("FR-01.01") == "needs_reverification"
        assert rec.status("FR-09.99") == "untouched"
