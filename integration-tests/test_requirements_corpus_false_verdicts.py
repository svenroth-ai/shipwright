"""The TWO false verdicts the campaign SPEC names (FV-1, FV-2).

Campaign "Requirements Catalog", written at S1. **FV-1 was flipped by S4**
(``iterate-2026-07-20-one-header-driven-parser``) and its assertions now pin the
corrected behaviour; FV-2 is still frozen and belongs to S6, so every FV-2
assertion below still pins behaviour that is WRONG on purpose. A baseline that
quietly corrected the bugs would make the campaign's behaviour-preserving claims
uncheckable.

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

    Pinned separately from the zero-row case on purpose, and the separation did
    its job: S4 flipped exactly the other one, and this assertion is unchanged
    across that commit. Keep it that way -- an `absent` project that starts
    FAILing is a regression, not progress.
    """
    assert _probe("t1", "absent")["status"] == "SKIP"


def test_fv1_zero_row_parse_now_fails_instead_of_skipping():
    """FLIPPED by S4 (was FROZEN-BUG FV-1): a populated spec now reaches T1.

    The `zero-row-parse` fixture holds a real requirement (FR-06.01) in a table
    whose columns are reordered. The old positional regex pinned
    Must|Should|May to data column 3, matched nothing, and returned [] -- and
    ``check_t1_all_spec_frs_mapped`` guards on `if not requirements`, a plain
    falsiness test that cannot distinguish "no spec" from "spec I could not
    read", so the FAIL branch was unreachable. The requirement existed, the RTM
    did not cover it, and T1 reported SKIP.

    The header-driven reader parses the row, so the guard is no longer reached
    and T1 reports the truth: uncovered.

    The GUARD is not fixed, only its trigger -- see the "HONEST LIMIT" note on
    FV-1 in ``requirements_corpus/frozen_bugs.py``. S5 owns making "present but
    unreadable" distinguishable from "absent".
    """
    finding = _probe("t1", "zero-row-parse")
    assert finding["status"] == "FAIL"
    assert "no FRs found" not in finding["evidence"]


def test_fv1_the_populated_state_is_distinguishable_from_the_empty_ones():
    """FLIPPED by S4 (was FROZEN-BUG FV-1).

    'no requirements tree', 'empty tree' and 'tree with a populated spec' are
    materially different situations. All three used to emit the identical
    verdict AND the identical evidence, so no operator reading the report could
    tell them apart.

    The two genuinely-empty states still (correctly) SKIP and still share their
    evidence -- that pair is NOT a bug and S4 deliberately did not touch it.
    The third has separated.
    """
    verdicts = {
        fixture: _probe("t1", fixture)
        for fixture in ("absent", "empty", "zero-row-parse")
    }
    assert {f: v["status"] for f, v in verdicts.items()} == {
        "absent": "SKIP", "empty": "SKIP", "zero-row-parse": "FAIL",
    }
    assert verdicts["absent"]["evidence"] == verdicts["empty"]["evidence"], (
        "absent and empty are both legitimately 'nothing to check' -- if these "
        "diverged, that is S5's work arriving early, not S4's"
    )
    assert verdicts["zero-row-parse"]["evidence"] != verdicts["absent"]["evidence"]


def test_fv1_t1_can_still_fail_when_rows_do_parse():
    """Control: T1 is not simply always-SKIP.

    Without this, the three assertions above would also pass if T1 were broken
    outright, and the corpus would be freezing a tautology rather than a bug.
    """
    assert _probe("t1", "mixed-shape")["status"] == "FAIL"


# ---------------------------------------------------------------------------
# FV-2 -- an empty requirement set reads GREEN
# ---------------------------------------------------------------------------

def test_fv2_d2_now_fails_when_an_event_references_a_nonexistent_fr():
    """FLIPPED by S6 (was FROZEN-BUG FV-2), the sharpest of the D-group three.

    With zero spec FRs, EVERY ``affected_frs`` reference in the event log is by
    definition stale -- the maximally red state. D2 nonetheless reported 'skip',
    because ``if not spec_frs: skip`` sat ABOVE the staleness loop and made the
    FAIL branch unreachable. Exactly the shape of FV-1: a falsiness guard placed
    early enough that the check it guards can never run.

    S6 moved the guard BELOW the loop, so it now only fires on the clean branch.
    Zero spec FRs plus an FR-referencing event FAILs; zero spec FRs plus no
    references at all still skips, because then there genuinely was nothing to
    compare -- and it says so rather than claiming every reference resolved.
    """
    result = _probe("group_d_empty", "absent")
    status, severity, detail, _evidence = result["D2_with_refs"]
    assert status == "fail"
    assert severity == "MEDIUM"
    assert "FR-99.99" in detail


def test_fv2_d1_d2_d4_still_skip_when_there_is_nothing_at_all_to_compare():
    """Control for the flip above -- and NOT itself a frozen bug.

    'No requirements and no events' is a real, legitimate state (a project before
    its first requirements run). Skipping there is correct; what FV-2 named was
    the false CLAIM, not the absence of a block. Without this assertion the flip
    above would also pass if D2 had been made unconditionally red, which would
    trade a false green for a false red.
    """
    result = _probe("group_d_empty", "absent")
    assert [result["D1"][0], result["D2"][0], result["D4"][0]] == [
        "skip", "skip", "skip",
    ]
    assert result["D2"][1] == "MEDIUM"
    # The skip NAMES which empty state produced it (S6): the `absent` fixture
    # has no planning tree at all, which is a different situation from a spec
    # whose every row was declined -- and D2 can now FAIL on the latter.
    assert "no spec.md" in result["D2"][2]


def test_fv2_group_i_skips_every_check_on_empty():
    """FROZEN-BUG (FV-2): every Group I check skips on zero rows.

    Note Group I is green-by-construction twice over: I1-I3 are advisory and
    emit 'pass' instead of 'fail' even on the non-empty path, so only I4 and I5
    can ever redden the audit.

    **PARTIALLY ADDRESSED BY S5, deliberately not flipped.** The verdict is
    still 'skip' -- Group I is detective-only and a repo with no requirements
    must not redden CI, so that half is correct and stays. What S5 changed is
    that the skip now names WHICH of six states produced it, so "no spec on
    disk" (this fixture) is no longer worded identically to "a well-formed table
    whose every id was declined". The silence FV-2 describes was the conflation,
    not the skip; see test_audit_group_i_states.py for the six states.

    I5 (Basis vocabulary) joined the group in S5.

    **S6 DELIBERATELY DID NOT FLIP THIS.** It flipped the two sites that emitted
    a positive claim over the empty set (D-orphan / D-layer) and the one whose
    early guard made its red branch unreachable (D2). Group I is neither: it is
    detective-only, its skip is honest about examining nothing, and S5 already
    made it name which of six states produced the skip. Reddening it would be a
    false red on a repo with no requirements yet, bought for no gain.
    """
    findings = _probe("group_i_empty", "absent")
    assert {f["check_id"] for f in findings} == {"I1", "I2", "I3", "I4", "I5"}
    assert {f["status"] for f in findings} == {"skip"}  # FROZEN-BUG (FV-2)
    # The state is now named rather than generic -- S5's half of FV-2.
    assert all("no spec.md found" in f["detail"] for f in findings)


def test_fv2_empty_manifest_no_longer_asserts_positive_coverage():
    """FLIPPED by S6 (was FROZEN-BUG FV-2), the sharpest site in the family --
    and NOT the one the campaign SPEC names.

    Every other empty-set guard at least said 'skip'. These two emitted **pass**,
    and the layer check stated a positive fact about a set it never examined:
    "every active FR is covered at its required layers", over zero FRs. A reader
    of the audit report could not distinguish that from a genuinely fully-covered
    project. That was the whole of FV-2 in one string.

    The argument that carried the flip: this repo already knows how to treat
    emptiness as a defect -- adopt_compliance A2 FAILs on no specs,
    campaign_status raises, design_checks returns not-ok -- so the green was a
    local inconsistency in the requirements plane, not a house style.

    D-layer now skips, and the skip NAMES the state. Deliberately not 'fail': a
    repo with no requirements yet is legitimate, so a hard verdict would swap a
    false green for a false red. What is removed is the claim, not the tolerance.

    **D-orphan was deliberately NOT flipped**, though it was pinned alongside
    D-layer here. Its sentence over an empty requirement set is TRUE rather than
    vacuous: had any test carried an @FR tag, every one would be absent-FR and
    would appear in `orphans`, so an empty list means there were no tagged tests
    -- a claim about the tag universe, which was examined. Flipping it also broke
    two unrelated pins (`test_orphan_passes_when_no_orphans`,
    `..._unmapped_alone_is_informational_not_accusation`), which is what surfaced
    that the two sites were being treated as one defect when they are not.
    """
    result = _probe("d_traceability_empty", "absent")
    assert result["layer"][0] == "skip"
    assert "nothing was examined" in result["layer"][2]
    assert "every active FR is covered" not in result["layer"][2]
    assert result["orphan"][0] == "pass"  # see docstring -- not vacuous


def test_fv2_a_populated_manifest_still_reaches_a_real_verdict():
    """Control: the empty guard must not swallow the populated path.

    Without this, the flip above would also pass if the two checks had been made
    unconditionally skip -- which would silence the coverage plane completely
    rather than stopping it lying about the empty set.
    """
    result = _probe("d_traceability_populated", "absent")
    assert result["layer"][0] == "pass"
    assert result["layer"][2] == "every active FR is covered at its required layers"
    assert result["orphan"][0] == "pass"
