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


def test_all_three_agree_on_the_shipped_shape():
    """The real-world case (no prose anywhere): I6, S5 and the cross-layer
    gate must read the identical criteria list — this is what AC-1 requires
    for every spec this repo actually ships."""
    assert _group_i_has_criteria(_SHIPPED, "FR-01.01") is True

    heading = spec_parser.parse_fr_headings(_SHIPPED)[0]
    assert heading.has_acceptance()

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
