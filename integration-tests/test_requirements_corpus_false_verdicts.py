"""Freeze the TWO false verdicts the campaign SPEC names (FV-1, FV-2).

Campaign "Requirements Catalog" sub-iterate S1. Every assertion in this file
pins behaviour that is WRONG. That is deliberate: campaign steps S2-S4 claim to
be behaviour-preserving, and a baseline that quietly corrected the bugs would
make that claim uncheckable.

**If an assertion here fails, do not "fix" it into agreement.** Either you have
changed the requirements machinery -- in which case say which change and why --
or you are on the step that is supposed to flip it, in which case update the
assertion and its FROZEN-BUG comment in the SAME commit.

Full rationale for each: ``requirements_corpus/frozen_bugs.py``.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from requirements_corpus.probe import ProbeFailed, probe  # noqa: E402


def _probe(name: str, fixture: str):
    """Fail the test loudly if the probe crashes -- never silently pass.

    Raises rather than calling ``pytest.fail`` so the function has exactly one
    exit path per branch. ``pytest.fail`` does raise, but nothing in the
    signature says so, and a reader (or a static analyser) sees a branch that
    falls through and returns ``None`` -- which on a harness whose whole point
    is "a crashed probe must never read as a passing check" is the wrong shape
    to leave lying around.
    """
    try:
        return probe(name, fixture)
    except ProbeFailed as exc:
        raise AssertionError(str(exc)) from exc


# ---------------------------------------------------------------------------
# FV-1 -- a spec parsing to ZERO rows makes T1 SKIP rather than FAIL
# ---------------------------------------------------------------------------

def test_fv1_absent_planning_tree_skips_correctly():
    """A project with no planning tree SHOULD skip. This one is not a bug.

    Pinned separately from the zero-row case on purpose: today T1 cannot tell
    the two apart, and S4 must flip only the other one. Keeping them apart means
    the S4 diff shows exactly which cause changed.
    """
    assert _probe("t1", "absent")["status"] == "SKIP"


def test_fv1_zero_row_parse_skips_instead_of_failing():
    """FROZEN-BUG (FV-1): a POPULATED spec that parses to zero rows -> SKIP.

    The `zero-row-parse` fixture holds a real requirement (FR-06.01) in a table
    whose columns are reordered. ``drift_parsers._FR_TABLE_RE`` pins
    Must|Should|May to data column 3, so it matches nothing and the collector
    returns []. ``check_t1_all_spec_frs_mapped`` guards on `if not requirements`
    -- a plain falsiness test that cannot distinguish "no spec" from "spec I
    could not read" -- so the FAIL branch below it is unreachable.

    The requirement exists. The RTM does not cover it. T1 reports SKIP.

    WRONG. Frozen anyway -- this is the baseline S2-S4 are measured against.
    Flipped by: S4 (header-driven parser; column order stops being load-bearing).
    """
    finding = _probe("t1", "zero-row-parse")
    assert finding["status"] == "SKIP"  # FROZEN-BUG (FV-1) -- should be FAIL
    assert "no FRs found" in finding["evidence"]


def test_fv1_three_distinct_states_are_indistinguishable():
    """FROZEN-BUG (FV-1): the evidence string cannot tell an operator which.

    'no requirements tree', 'empty tree' and 'tree with an unparseable spec' are
    materially different situations. Two are fine; the third means the control
    plane is blind. All three currently emit the identical verdict AND the
    identical evidence, so no operator reading the report can tell them apart.

    Flipped by: S4.
    """
    verdicts = {
        fixture: _probe("t1", fixture)
        for fixture in ("absent", "empty", "zero-row-parse")
    }
    statuses = {f: v["status"] for f, v in verdicts.items()}
    assert statuses == {
        "absent": "SKIP", "empty": "SKIP", "zero-row-parse": "SKIP",
    }
    evidence = {v["evidence"] for v in verdicts.values()}
    assert len(evidence) == 1, (
        "the three states became distinguishable -- if this is S4, update the "
        "FROZEN-BUG comments above in the same commit"
    )


def test_fv1_t1_can_still_fail_when_rows_do_parse():
    """Control: T1 is not simply always-SKIP.

    Without this, the three assertions above would also pass if T1 were broken
    outright, and the corpus would be freezing a tautology rather than a bug.
    """
    assert _probe("t1", "mixed-shape")["status"] == "FAIL"


# ---------------------------------------------------------------------------
# FV-2 -- an empty requirement set reads GREEN
# ---------------------------------------------------------------------------

def test_fv2_group_d_guards_skip_on_empty_requirements():
    """FROZEN-BUG (FV-2): D1/D2/D4 skip rather than fail on zero requirements.

    D2 is the sharpest of the three: with zero spec FRs, EVERY ``affected_frs``
    reference in the event log is by definition stale -- the maximally red
    state. The guard returns 'skip'.

    Flipped by: S6.
    """
    result = _probe("group_d_empty", "absent")
    assert [result["D1"][0], result["D2"][0], result["D4"][0]] == [
        "skip", "skip", "skip",
    ]  # FROZEN-BUG (FV-2)
    assert result["D2"][1] == "MEDIUM"


def test_fv2_group_i_skips_every_check_on_empty():
    """FROZEN-BUG (FV-2): all four Group I checks skip on zero rows.

    Note Group I is green-by-construction twice over: I1-I3 are advisory and
    emit 'pass' instead of 'fail' even on the non-empty path, so only I4 can
    ever redden the audit.

    Flipped by: S6.
    """
    findings = _probe("group_i_empty", "absent")
    assert {f["check_id"] for f in findings} == {"I1", "I2", "I3", "I4"}
    assert {f["status"] for f in findings} == {"skip"}  # FROZEN-BUG (FV-2)


def test_fv2_empty_manifest_asserts_positive_coverage():
    """FROZEN-BUG (FV-2), the sharpest site -- and NOT the one the SPEC names.

    Every other empty-set guard at least says 'skip'. These two emit **pass**,
    and the layer check states a positive fact about a set it never examined:
    "every active FR is covered at its required layers", over zero FRs.

    A reader of the audit report cannot distinguish this from a genuinely
    fully-covered project. That is the whole of FV-2 in one string.

    Worth noting this repo already knows how to treat emptiness as a defect --
    adopt_compliance A2 FAILs on no specs, campaign_status raises,
    design_checks returns not-ok. So this is a local inconsistency in the
    requirements plane, not a house style. That is the argument S6 will need.

    Flipped by: S6.
    """
    result = _probe("d_traceability_empty", "absent")
    assert result["orphan"][0] == "pass"  # FROZEN-BUG (FV-2)
    assert result["layer"][0] == "pass"   # FROZEN-BUG (FV-2)
    assert result["layer"][2] == "every active FR is covered at its required layers"
