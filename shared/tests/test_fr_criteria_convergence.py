"""All three FR-criteria readers agree (campaign REQ3.04, sub-iterate R0).

``lib.spec_parser`` (S5), ``tools.verifiers._layer_coverage_ac`` (the
cross-layer fold gate) and
``plugins/shipwright-compliance/scripts/audit/group_i_criteria`` (I6) used to
each walk a spec's acceptance-criteria bullets on their own, and disagreed
about what counted — see the module docstrings of ``lib.fr_criteria`` and
``group_i_criteria`` for the history. All three now delegate to
``lib.fr_criteria``; this test pins that on one shared input, they still read
the SAME criteria list.

``group_i_criteria.has_criteria`` is a pure passthrough to
``fr_criteria.has_criteria`` (see its own plugin test suite, which pins the
delegation), so exercising ``fr_criteria`` directly here covers it without
crossing this repo's pytest test-root boundary (ADR-044): importing the
compliance plugin's ``scripts`` package from this root would give ``scripts``
two identities in one session.
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


def test_all_three_readers_agree_on_the_same_criteria_list():
    expected = fr_criteria.criteria_for(_SPEC, "FR-01.01")
    assert expected  # sanity: the fixture actually has criteria

    # spec_parser (S5) — via parse_fr_headings' shipped-form fallback (S2).
    heading = spec_parser.parse_fr_headings(_SPEC)[0]
    assert heading.acceptance.split("\n") == expected

    # group_i_criteria (I6) — a pure passthrough, so this IS its answer.
    assert fr_criteria.has_criteria(_SPEC, "FR-01.01") is True

    # _layer_coverage_ac (cross-layer fold gate) — same list, digested.
    joined = "\n".join(expected)
    assert criteria_digests(_SPEC)["FR-01.01"] == hashlib.sha256(
        joined.encode("utf-8"),
    ).hexdigest()


def test_prose_before_bullets_is_a_deliberate_scoping_difference_not_a_bug():
    """External plan review (openai, HIGH, 2026-08-25) flagged that
    ``criteria_for``/``has_criteria`` (I6, the cross-layer gate) read a bullet
    list even when prose precedes it, while ``leading_criteria`` (S5's
    fallback) requires strict adjacency and would reject the same input.

    This is intentional, not a missed convergence — see ``fr_criteria``'s own
    module docstring ("Two entry points, not one..."): I6/the cross-layer gate
    already scan an EXPLICITLY FR-anchored section (never a broad free-text
    tree), where a `**Description:**`-style paragraph ahead of the bullets is
    a legitimate, pre-existing shape (group_i's original behaviour, unchanged
    by this campaign). S5's fallback alone needs the stricter gate, because
    IT ALONE walks `.shipwright/planning/iterate/*.md` — arbitrary prose
    documents where an unrelated bullet list must never be misread as an
    FR's acceptance. Pinned here so the divergence stays a stated design
    choice, not an unstated side effect.
    """
    spec_with_prose_gap = (
        "## Acceptance Criteria\n\n"
        "### FR-01.01 — Title\n\n"
        "**Description:** some prose ahead of the bullets.\n\n"
        "- (E) Given a change, when it runs, then it works.\n"
    )

    # I6 / the cross-layer gate: permissive, reads the block regardless of
    # what precedes the bullets within it.
    assert fr_criteria.has_criteria(spec_with_prose_gap, "FR-01.01") is True

    # S5's fallback: adjacency-gated, sees the prose first and stops — the
    # heading has NO acceptance via this path (the labelled form doesn't
    # apply here either, since "Description" is not an acceptance label).
    heading = spec_parser.parse_fr_headings(spec_with_prose_gap)[0]
    assert not heading.has_acceptance()
