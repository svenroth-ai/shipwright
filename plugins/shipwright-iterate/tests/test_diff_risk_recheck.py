"""Decision-logic tests for the post-Build risk re-check (`diff_risk_recheck`).

The campaign `sub-iterate-runner` classifies ONCE, at Step 2, from the spec *text*
before code exists, so the diff-driven detectors — reached only by the Stage-2 Repo
Scout it never runs — cannot fire for a campaign unit.

Everything here is in-process and pure: subprocess-only tests measure 0% against
the <80% diff-coverage gate. The git layer and CLI live in
`test_diff_change_set.py`; composition lives in the integration test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import diff_risk_recheck as drr  # noqa: E402

HOOK = "plugins/shipwright-iterate/hooks/hooks.json"
WORKFLOW = ".github/workflows/ci.yml"
LOCKFILE = "uv.lock"
ENVFILE = "src/.env.local"
INERT = "src/components/Button.tsx"


# ---------------------------------------------------------------------------
# detect_diff_flags — the four detectors, over a file list
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_no_flags_on_inert_paths():
    assert drr.detect_diff_flags([INERT]) == []


@pytest.mark.covers("FR-01.11")
def test_cross_component_detected():
    assert "cross_component" in drr.detect_diff_flags([HOOK])


@pytest.mark.covers("FR-01.11")
def test_ci_supplychain_detected():
    assert "touches_ci_supplychain" in drr.detect_diff_flags([WORKFLOW])


@pytest.mark.covers("FR-01.11")
def test_touches_build_detected():
    assert "touches_build" in drr.detect_diff_flags([LOCKFILE])


@pytest.mark.covers("FR-01.11")
def test_io_boundary_detected():
    assert "touches_io_boundary" in drr.detect_diff_flags([ENVFILE])


@pytest.mark.covers("FR-01.11")
def test_flags_are_sorted_and_deduped():
    """Duplicate inputs must not yield duplicate flags."""
    flags = drr.detect_diff_flags([HOOK, HOOK, WORKFLOW])
    assert flags == sorted(set(flags))
    assert flags.count("cross_component") == 1


@pytest.mark.covers("FR-01.11")
def test_windows_separators_normalized():
    """git on Windows may emit backslashes."""
    assert "cross_component" in drr.detect_diff_flags(
        ["plugins\\shipwright-iterate\\hooks\\hooks.json"]
    )


@pytest.mark.covers("FR-01.11")
def test_quoted_non_ascii_path_still_fires():
    """A leading core.quotePath quote defeats the `^` anchor."""
    assert "touches_ci_supplychain" in drr.detect_diff_flags(
        ['".github/workflows/f\\303\\266rderung.yml"']
    )


@pytest.mark.covers("FR-01.11")
def test_empty_and_none_are_inert():
    assert drr.detect_diff_flags([]) == []
    assert drr.detect_diff_flags(None) == []


# ---------------------------------------------------------------------------
# recheck — floors, ordering, upgrade semantics
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_cross_component_floors_at_medium():
    out = drr.recheck([HOOK], stage1_complexity="small")
    assert out["complexity_floor"] == "medium"
    assert out["effective_complexity"] == "medium"
    assert out["upgraded"] is True


@pytest.mark.covers("FR-01.11")
def test_floor_never_lowers_stage1():
    """The re-check may only raise: medium + a small floor stays medium."""
    out = drr.recheck([LOCKFILE], stage1_complexity="medium")
    assert out["complexity_floor"] == "small"
    assert out["effective_complexity"] == "medium"
    assert out["upgraded"] is False


@pytest.mark.covers("FR-01.11")
def test_ordering_is_semantic_not_lexicographic():
    """Lexicographically "small" > "medium": a string `max()` would DOWNGRADE."""
    out = drr.recheck([HOOK], stage1_complexity="small")
    assert out["effective_complexity"] == "medium"


@pytest.mark.covers("FR-01.11")
def test_no_flags_leaves_stage1_untouched():
    out = drr.recheck([INERT], stage1_complexity="small")
    assert out["risk_flags"] == []
    assert out["complexity_floor"] == "trivial"
    assert out["effective_complexity"] == "small"
    assert out["upgraded"] is False


@pytest.mark.covers("FR-01.11")
def test_unknown_stage1_complexity_rejected():
    """An unexpected Stage-1 value must not reach the F5c record."""
    with pytest.raises(ValueError, match="complexity"):
        drr.recheck([INERT], stage1_complexity="enormous")


# ---------------------------------------------------------------------------
# Escalation — the operator decision (2026-08-01)
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_ci_supplychain_escalates():
    out = drr.recheck([WORKFLOW], stage1_complexity="small")
    esc = out["escalate"]
    assert esc["required"] is True
    assert esc["reason_code"] == "ci_supplychain_requires_operator"
    assert esc["paths"] == [WORKFLOW]


@pytest.mark.covers("FR-01.11")
def test_escalation_paths_list_only_ci_files():
    """The operator gets the CI files, not the whole diff."""
    out = drr.recheck([WORKFLOW, HOOK, INERT], stage1_complexity="small")
    assert out["escalate"]["paths"] == [WORKFLOW]


@pytest.mark.covers("FR-01.11")
def test_non_ci_flags_do_not_escalate():
    """cross_component raises complexity; it does NOT stop the unit."""
    out = drr.recheck([HOOK], stage1_complexity="trivial")
    assert out["escalate"]["required"] is False
    assert out["escalate"]["reason_code"] is None
    assert out["escalate"]["paths"] == []


@pytest.mark.covers("FR-01.11")
def test_escalation_still_reports_flags_and_complexity():
    """An escalated result must still carry its analysis, not just the stop."""
    out = drr.recheck([WORKFLOW, HOOK], stage1_complexity="trivial")
    assert out["escalate"]["required"] is True
    # hooks.json is deliberately in BOTH pattern tuples — it is cross-component
    # machinery AND a serialized IO boundary — so it raises two flags, not one.
    assert set(out["risk_flags"]) == {
        "touches_ci_supplychain",
        "cross_component",
        "touches_io_boundary",
    }
    assert out["effective_complexity"] == "medium"


# ---------------------------------------------------------------------------
# plan_review_required — AC5, the Step 3.5 trigger mirrored onto Step 3.7's
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_plan_review_required_on_medium():
    assert drr.recheck([INERT], stage1_complexity="medium")["plan_review_required"]


@pytest.mark.covers("FR-01.11")
def test_plan_review_required_on_risk_flag():
    assert drr.recheck([LOCKFILE], stage1_complexity="trivial")["plan_review_required"]


@pytest.mark.covers("FR-01.11")
def test_plan_review_required_on_large_diff():
    """The arm Step 3.7 had and Step 3.5 lacked — the whole point of AC5."""
    out = drr.recheck([INERT], stage1_complexity="small", diff_loc=101)
    assert out["plan_review_required"] is True


@pytest.mark.covers("FR-01.11")
def test_plan_review_not_required_below_every_threshold():
    out = drr.recheck([INERT], stage1_complexity="small", diff_loc=100)
    assert out["plan_review_required"] is False


@pytest.mark.covers("FR-01.11")
def test_diff_loc_boundary_is_strictly_greater_than_100():
    """Mirrors Step 3.7's documented `> 100` exactly — not `>=`."""
    assert drr.recheck([INERT], "trivial", diff_loc=100)["plan_review_required"] is False
    assert drr.recheck([INERT], "trivial", diff_loc=101)["plan_review_required"] is True


# ---------------------------------------------------------------------------
# Stage-1 flag union — the regression the Stage-2 review caught
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_stage1_flags_are_unioned_not_replaced():
    """Seven canonical flags have NO diff-driven detector. Replacing Stage 1's set
    would take a `touches_auth` spec whose diff touches only a page component from
    RUNNING the plan review to SKIPPING it — narrowing the gate this widens."""
    out = drr.recheck([INERT], "small", stage1_flags=["touches_auth"])
    assert "touches_auth" in out["risk_flags"]
    assert out["plan_review_required"] is True


@pytest.mark.covers("FR-01.11")
def test_stage1_and_diff_flags_both_survive():
    out = drr.recheck([HOOK], "small", stage1_flags=["touches_billing"])
    assert {"touches_billing", "cross_component"} <= set(out["risk_flags"])
    # The floor still comes from the DIFF flags only: Stage 1 already applied its
    # own flags' floors when it produced `stage1_complexity`.
    assert out["complexity_floor"] == "medium"
    assert out["diff_risk_flags"] == sorted(drr.detect_diff_flags([HOOK]))


@pytest.mark.covers("FR-01.11")
def test_stage1_flags_default_to_empty():
    assert drr.recheck([INERT], "small")["risk_flags"] == []

@pytest.mark.parametrize("raw,expected", [
    ("touches_auth,touches_rls", ["touches_auth", "touches_rls"]),
    ("touches_auth\ntouches_rls", ["touches_auth", "touches_rls"]),
    ("", []),
    (None, []),
    ("  touches_auth  ,, ", ["touches_auth"]),
    # `classify_complexity` emits risk_flags as a JSON ARRAY, so this is what the
    # obvious interpolation of Step 2's output actually looks like. A naive split
    # yields '["touches_auth"' — which still makes plan_review_required fire (so
    # AC5 looks fine) while Step 3.8's lookup for the NAMED touches_io_boundary
    # silently misses.
    ('["touches_auth", "touches_io_boundary"]',
     ["touches_auth", "touches_io_boundary"]),
    ("['touches_auth']", ["touches_auth"]),
    ("[]", []),
])
@pytest.mark.covers("FR-01.11")
def test_split_flags_accepts_both_separators_and_json_arrays(raw, expected):
    assert drr._split_flags(raw) == expected


@pytest.mark.covers("FR-01.11")
def test_json_array_flags_survive_by_name_not_just_by_count():
    """The bug is a NAMED-flag lookup failing while truthiness passes."""
    out = drr.recheck(
        [INERT], "small",
        stage1_flags=drr._split_flags('["touches_io_boundary"]'),
    )
    assert "touches_io_boundary" in out["risk_flags"]


# ---------------------------------------------------------------------------
# The CI escalation must be exitable (doubt finding D1)
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.11")
def test_recorded_ack_clears_the_stop_but_keeps_the_finding():
    """Without this the handback never terminates: ack → re-run → Build re-creates
    the CI edit → escalate again."""
    out = drr.recheck([WORKFLOW], "small", ack_recorded=True)
    assert out["escalate"]["required"] is False
    assert out["escalate"]["reason_code"] is None
    assert out["ci_ack_recorded"] is True
    assert out["escalate"]["paths"] == [WORKFLOW]
    assert "touches_ci_supplychain" in out["risk_flags"]


@pytest.mark.covers("FR-01.11")
def test_ack_path_is_the_documented_per_run_location():
    """Must match where the ack is written and where F11 looks for it."""
    p = drr.ack_path(Path("/proj"), "iterate-2026-08-01-x")
    assert p.as_posix().endswith(
        ".shipwright/planning/iterate/iterate-2026-08-01-x/ci_supplychain_ack.json"
    )
