"""S5 and the cross-layer gate agree via ``lib.fr_criteria`` (campaign
REQ3.04, sub-iterate R0).

``lib.spec_parser`` (S5) and ``tools.verifiers._layer_coverage_ac`` (the
cross-layer fold gate) used to each walk a spec's acceptance-criteria
bullets on their own, and disagreed about what counted — see the module
docstrings of ``lib.fr_criteria`` and ``group_i_criteria`` for the history.
Both now delegate to ``lib.fr_criteria``; this test pins that on the shipped
shape they still read the SAME criteria list, and that the one documented
``strict=False`` exception behaves as specified.

This file cannot ALSO invoke ``group_i_criteria`` (I6) directly: doing so
from this root would give the compliance plugin's ``scripts`` package a
second identity in this pytest process (ADR-044). The genuine three-way test
— I6's real module, S5, and the cross-layer gate, all invoked through their
real entry points on the same inputs — lives in
``integration-tests/test_fr_criteria_three_way_convergence.py``, which is a
different pytest root built for exactly this cross-plugin-boundary case
(Stage-1 spec review, 2026-08-25: a stand-in that never calls I6's real
module does not test I6).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from lib import fr_criteria  # noqa: E402
from lib import spec_parser  # noqa: E402
from verifiers._layer_coverage_ac import criteria_digests  # noqa: E402

_SPEC = (
    "## Acceptance Criteria\n\n"
    "### FR-01.01 — Title\n\n"
    "- (E) Given a change, when it runs, then it works.\n"
    "- (E) Given a failure, when it runs, then it stops.\n"
)


def test_s5_and_cross_layer_agree_on_the_same_criteria_list():
    expected = fr_criteria.criteria_for(_SPEC, "FR-01.01")
    assert expected  # sanity: the fixture actually has criteria

    # spec_parser (S5) — via parse_fr_headings' shipped-form fallback (S2),
    # always the strict/adjacency default.
    heading = spec_parser.parse_fr_headings(_SPEC)[0]
    assert heading.acceptance.split("\n") == expected

    # _layer_coverage_ac (cross-layer fold gate) — same list, digested. It
    # calls strict=False, but the shipped shape (no prose before the
    # bullets) has nothing for strict=False to disagree with strict=True on.
    joined = "\n".join(expected)
    assert criteria_digests(_SPEC)["FR-01.01"] == hashlib.sha256(
        joined.encode("utf-8"),
    ).hexdigest()


def test_strict_false_is_the_one_documented_permissive_exception():
    """Since 2026-08-25 (Stage-1 spec review), ``criteria_for``/``has_criteria``
    default to the SAME adjacency gate ``leading_criteria`` (S5) uses —
    ``strict=False`` is an explicit, narrow opt-out, not a silent second
    default. This module-level test pins ``fr_criteria``'s own contract; the
    two REAL call sites that actually pass ``strict=False`` (I6's
    ``has_criteria``, the cross-layer gate's ``criteria_digests``) are
    exercised through their own real entry points in
    ``integration-tests/test_fr_criteria_three_way_convergence.py``.
    """
    spec_with_prose_gap = (
        "## Acceptance Criteria\n\n"
        "### FR-01.01 — Title\n\n"
        "**Description:** some prose ahead of the bullets.\n\n"
        "- (E) Given a change, when it runs, then it works.\n"
    )

    # Default (strict=True): adjacency-gated, agrees with S5's fallback.
    assert fr_criteria.has_criteria(spec_with_prose_gap, "FR-01.01") is False
    heading = spec_parser.parse_fr_headings(spec_with_prose_gap)[0]
    assert not heading.has_acceptance()

    # Explicit strict=False: the documented, tested exception.
    assert fr_criteria.has_criteria(spec_with_prose_gap, "FR-01.01", strict=False) is True


def test_the_one_leading_italic_attribution_line_does_not_disqualify_the_run():
    """`/shipwright-adopt`'s REAL, shipped shape
    (`plugins/shipwright-adopt/scripts/lib/spec_document.py:181-186`): every
    criteria-bearing FR renders a single whole-line italic attribution
    (`_Source: tests._` / `_Source: enrichment._`,
    `generate_adoption_artifacts.py:308`/`:376`) between the heading and its
    bullets — not a hypothetical. Before this fix, `strict=True`'s adjacency
    gate (the shared default since Stage-1) saw that line as disqualifying
    prose and returned `[]` for EVERY criteria-bearing FR in real adopt
    output, while `strict=False` callers (I6, the cross-layer gate) still
    saw the criteria — AC-1's divergence, reintroduced on real producer
    bytes, not a test fixture (Stage-3 doubt review, high, 2026-08-25)."""
    adopt_shape = (
        "## Acceptance Criteria\n\n"
        "### FR-01.01 — Title\n\n"
        "_Source: tests._\n\n"
        "- (E) Given a change, when it runs, then it works.\n"
        "- (E) Given a failure, when it runs, then it stops.\n"
    )
    expected = fr_criteria.criteria_for(adopt_shape, "FR-01.01")
    assert expected  # sanity: strict=True's default now finds it

    heading = spec_parser.parse_fr_headings(adopt_shape)[0]
    assert heading.has_acceptance()
    assert heading.acceptance.split("\n") == expected

    joined = "\n".join(expected)
    assert criteria_digests(adopt_shape)["FR-01.01"] == hashlib.sha256(
        joined.encode("utf-8"),
    ).hexdigest()

    # A SECOND non-bullet line still disqualifies the run — this does not
    # reopen the door strict=True closed.
    two_prose_lines = (
        "## Acceptance Criteria\n\n"
        "### FR-01.01 — Title\n\n"
        "_Source: tests._\n\n"
        "Some genuine prose paragraph.\n\n"
        "- (E) Given a change, when it runs, then it works.\n"
    )
    assert fr_criteria.has_criteria(two_prose_lines, "FR-01.01") is False
