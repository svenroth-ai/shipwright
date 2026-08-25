"""All three FR-criteria readers, invoked through their REAL entry points, on
inputs that distinguish adjacency behaviour (Stage-1 spec review, 2026-08-25).

``lib.spec_parser`` (S5), ``tools.verifiers._layer_coverage_ac`` (the
cross-layer fold gate) and
``plugins/shipwright-compliance/scripts/audit/group_i_criteria`` (I6) used to
each walk a spec's acceptance-criteria bullets on their own script, and
disagreed about what counted. All three now delegate to ``lib.fr_criteria``
— see its module docstring for the shared ``strict`` contract this file pins
end to end.

``shared/tests/test_fr_criteria_convergence.py`` already pins S5 and the
cross-layer gate against each other and against ``lib.fr_criteria`` directly,
but CANNOT also invoke I6's real module: importing
``plugins/shipwright-compliance``'s ``scripts`` package from that root would
give ``scripts`` two identities in one pytest process (ADR-044). This root is
built for exactly that cross-plugin-boundary case, so I6 is exercised here as
a real subprocess through its actual import path — never a stand-in.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLIANCE_PLUGIN = REPO_ROOT / "plugins" / "shipwright-compliance"
SHARED_SCRIPTS = REPO_ROOT / "shared" / "scripts"

if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))
if str(SHARED_SCRIPTS / "tools") not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS / "tools"))

from lib import spec_parser  # noqa: E402
from verifiers._layer_coverage_ac import criteria_digests  # noqa: E402


def _group_i_has_criteria(content: str, fr_id: str) -> bool:
    """I6's real ``has_criteria``, run as a subprocess.

    A subprocess has its own, fresh ``sys.modules`` — the only way to import
    the compliance plugin's ``scripts.audit.group_i_criteria`` (an absolute
    import needing ``plugins/shipwright-compliance`` on ``sys.path``) without
    risking a ``scripts`` package identity collision in THIS test process,
    which may already have other plugins' ``scripts`` packages loaded.

    ``content`` travels over stdin (arbitrary text, incl. newlines); ``fr_id``
    over argv — a clean, unambiguous channel split for a one-shot ``-c`` run.
    """
    script = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(COMPLIANCE_PLUGIN)!r})\n"
        "from scripts.audit.group_i_criteria import has_criteria\n"
        "print(json.dumps(has_criteria(sys.stdin.read(), sys.argv[1])))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, fr_id],
        input=content,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


def _group_i_criteria_for(content: str, fr_id: str) -> list[str]:
    """I6's real criteria LIST (not just the boolean), via the same
    subprocess bridge — code review, medium, 2026-08-25: AC-1 requires the
    same criteria LIST across readers, not merely the same true/false.

    Calls I6's OWN ``criteria_for`` entry point, not
    ``group_i_criteria.fr_criteria.criteria_for`` directly — the latter only
    proves the shared module is reachable through this module's attribute,
    not that I6's own contract returns the right list (doubt-review round 1,
    2026-08-25, trg-467b7b2f)."""
    script = (
        "import sys, json\n"
        f"sys.path.insert(0, {str(COMPLIANCE_PLUGIN)!r})\n"
        "from scripts.audit.group_i_criteria import criteria_for\n"
        "print(json.dumps(criteria_for(sys.stdin.read(), sys.argv[1])))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, fr_id],
        input=content,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


_SHIPPED = (
    "## Acceptance Criteria\n\n"
    "### FR-01.01 — Title\n\n"
    "- (E) Given a change, when it runs, then it works.\n"
    "- (E) Given a failure, when it runs, then it stops.\n"
)

_PROSE_BEFORE_BULLETS = (
    "## Acceptance Criteria\n\n"
    "### FR-01.01 — Title\n\n"
    "**Description:** some prose ahead of the bullets.\n\n"
    "- (E) Given a change, when it runs, then it works.\n"
)

_PROSE_BETWEEN_TWO_LISTS = (
    "## Acceptance Criteria\n\n"
    "### FR-01.01 — Title\n\n"
    "- (E) Given a change, when it runs, then it works.\n"
    "\n"
    "Some note in between.\n"
    "\n"
    "- (E) Given a later, non-adjacent bullet, when read, then it should not "
    "reach S5's fallback.\n"
)

#: `/shipwright-adopt`'s REAL, shipped per-FR shape — EXACT, not paraphrased
#: (`plugins/shipwright-adopt/scripts/lib/spec_document.py:181-186`, emitted
#: whenever an FR carries mined/enriched criteria,
#: `generate_adoption_artifacts.py:308`/`:376`). Stage-3 doubt review, high,
#: 2026-08-25: the leading `_Source: tests._` line made `strict=True`'s
#: adjacency gate (the shared default) read ZERO criteria here, while I6/the
#: cross-layer gate (`strict=False`) still saw them.
_ADOPT_ATTRIBUTION_SHAPE = (
    "## Acceptance Criteria\n\n"
    "### FR-01.01 — Title\n\n"
    "_Source: tests._\n\n"
    "- (E) Given a change, when it runs, then it works.\n"
    "- (E) Given a failure, when it runs, then it stops.\n"
)

#: A DEEPER heading nested inside a parent anchor's own span — no wrapping
#: ``## Acceptance Criteria`` heading, so the whole-document fail-safe scans
#: it directly (Stage-3 doubt review, medium, 2026-08-25): the old
#: ``iter_anchored_blocks`` jumped straight to the parent block's end
#: (``i = j``), so ``### FR-01.02`` never got its own turn as an anchor and
#: had no digest entry on EITHER side of a diff.
_NESTED_FR_HEADING = (
    "# Spec\n\n"
    "## FR-01.01 — Parent\n\n"
    "- (E) parent criterion\n\n"
    "### FR-01.02 — Nested\n\n"
    "- (E) nested criterion\n"
)


def test_all_three_agree_on_the_shipped_shape():
    """The real-world case (no prose anywhere): I6, S5 and the cross-layer
    gate must read the identical criteria LIST — not merely all-truthy or
    all-different-from-empty — this is what AC-1 requires for every spec
    this repo actually ships. A delegation regression that silently changed
    I6's returned list (lost `(E)`-stripping, a dropped placeholder rule,
    …) would still pass a boolean-only check; it must not pass this one."""
    i6_list = _group_i_criteria_for(_SHIPPED, "FR-01.01")
    assert i6_list  # sanity: I6 found something

    heading = spec_parser.parse_fr_headings(_SHIPPED)[0]
    assert heading.has_acceptance()
    assert "\n".join(i6_list) == heading.acceptance  # S5's exact list, not just non-empty

    i6_digest = hashlib.sha256("\n".join(i6_list).encode("utf-8")).hexdigest()
    assert criteria_digests(_SHIPPED)["FR-01.01"] == i6_digest  # cross-layer's exact list too
    assert criteria_digests(_SHIPPED)["FR-01.01"] != criteria_digests(
        "## Acceptance Criteria\n\n### FR-01.01 — Title\n\nnothing yet\n",
    )["FR-01.01"]


def test_prose_before_bullets_is_a_documented_permissive_exception():
    """I6 and the cross-layer gate both keep a narrow, tested tolerance for a
    ``**Description:**`` paragraph ahead of the bullets (each has its own
    pre-existing pin: ``test_legacy_bold_acceptance_label_still_counts``,
    ``test_prose_outside_a_criterion_is_not_a_criterion_change``). S5's
    fallback does NOT extend that tolerance — it alone walks free-text
    ``.shipwright/planning/iterate/*.md`` documents where an unrelated
    bullet list must never be misread as an FR's acceptance. This is a
    stated, tested divergence, not an unstated one (Stage-1 spec review,
    2026-08-25)."""
    assert _group_i_has_criteria(_PROSE_BEFORE_BULLETS, "FR-01.01") is True

    prose_digest = criteria_digests(_PROSE_BEFORE_BULLETS)["FR-01.01"]
    empty_digest = criteria_digests(
        "## Acceptance Criteria\n\n### FR-01.01 — Title\n\nnothing yet\n",
    )["FR-01.01"]
    assert prose_digest != empty_digest  # the cross-layer gate found it too

    heading = spec_parser.parse_fr_headings(_PROSE_BEFORE_BULLETS)[0]
    assert not heading.has_acceptance()  # S5 does not


def test_prose_between_two_bullet_lists_only_s5_reads_the_first():
    """The adjacency-bounded fallback (external code review, 2026-08-25) reads
    ONLY the leading, contiguous bullet run; a later list past an interior
    prose line never reaches it. I6 and the cross-layer gate scan the whole
    anchored block (the documented permissive exception) and legitimately
    see both lists — this is the same pre-existing behaviour
    ``test_prose_outside_a_criterion_is_not_a_criterion_change`` already
    relies on, extended here to a second bullet list rather than a bare
    note."""
    assert _group_i_has_criteria(_PROSE_BETWEEN_TWO_LISTS, "FR-01.01") is True

    heading = spec_parser.parse_fr_headings(_PROSE_BETWEEN_TWO_LISTS)[0]
    assert heading.has_acceptance()
    # S5 reads ONLY the first list's one criterion, not both.
    assert len(heading.acceptance.split("\n")) == 1
    assert "non-adjacent" not in heading.acceptance

    # The cross-layer gate's digest differs from the single-list shipped
    # shape's digest — it picked up the second list too.
    assert criteria_digests(_PROSE_BETWEEN_TWO_LISTS)["FR-01.01"] != criteria_digests(
        _SHIPPED,
    )["FR-01.01"]


def test_all_three_agree_on_the_real_adopt_attribution_shape():
    """`/shipwright-adopt`'s REAL per-FR shape inserts a single whole-line
    italic attribution between the heading and its bullets whenever an FR
    carries mined or enriched criteria — not a hypothetical, every
    criteria-bearing FR in real adopt output takes this exact shape. Before
    the Stage-3 doubt-review fix, `strict=True`'s adjacency gate (the shared
    default since Stage-1) read this attribution line as disqualifying
    prose and returned `[]` for every one of them, while I6/the cross-layer
    gate (`strict=False`) still saw the criteria — AC-1's divergence,
    reintroduced on real producer bytes, not a test fixture (Stage-3 doubt
    review, high, 2026-08-25)."""
    i6_list = _group_i_criteria_for(_ADOPT_ATTRIBUTION_SHAPE, "FR-01.01")
    assert i6_list  # sanity: I6 found something

    heading = spec_parser.parse_fr_headings(_ADOPT_ATTRIBUTION_SHAPE)[0]
    assert heading.has_acceptance()  # S5's adjacency gate now tolerates it too
    assert "\n".join(i6_list) == heading.acceptance

    i6_digest = hashlib.sha256("\n".join(i6_list).encode("utf-8")).hexdigest()
    assert criteria_digests(_ADOPT_ATTRIBUTION_SHAPE)["FR-01.01"] == i6_digest


def test_a_nested_fr_heading_still_yields_its_own_anchor_for_i6_too():
    """A DEEPER heading nested inside a parent anchor's span (`### FR-01.02`
    inside `## FR-01.01`) must still get its own block — the old
    `iter_anchored_blocks` jumped straight past it (`i = j`), so it was
    swallowed into the parent's span and never anchored at all: no digest
    entry on either side of a diff, and `criteria_changed_keys` could never
    see it change (Stage-3 doubt review, medium, 2026-08-25). Both `criteria_
    digests` (the cross-layer gate) and I6's real `has_criteria` must see
    BOTH ids."""
    digests = criteria_digests(_NESTED_FR_HEADING)
    assert "FR-01.01" in digests
    assert "FR-01.02" in digests

    assert _group_i_has_criteria(_NESTED_FR_HEADING, "FR-01.01") is True
    assert _group_i_has_criteria(_NESTED_FR_HEADING, "FR-01.02") is True


def test_i6_own_entry_point_sees_the_widened_bullet_semantics_too():
    """I6's OWN ``has_criteria``/``criteria_for`` (via ``group_i_criteria``'s
    real module, not a bypass) must see the same widened bullet forms
    ``shared/tests/test_fr_criteria_parsing.py`` pins on ``fr_criteria``
    directly: a numbered-list marker counts, a placeholder-only bullet does
    not (trg-968e4d87)."""
    numbered = (
        "### FR-01.01 — Title\n\n"
        "1. Given a change, when it runs, then it works.\n"
    )
    assert _group_i_has_criteria(numbered, "FR-01.01") is True
    assert _group_i_criteria_for(numbered, "FR-01.01") == [
        "Given a change, when it runs, then it works.",
    ]

    placeholder_only = "### FR-01.01 — Title\n\n- TBD\n"
    assert _group_i_has_criteria(placeholder_only, "FR-01.01") is False
