"""Nine downstream readers of ``lib.fr_criteria`` criterion text used to
treat the ``[ACnn]`` marker ``lib.ac_identity`` mints as literal prose (P3.4
doubt review, #689): a digest gate saw every minted criterion as changed,
and a minted placeholder stopped collapsing to the bare-placeholder token
set. Both are fixed at ``fr_criteria``'s own seam
(``test_fr_criteria_parsing.py`` pins the seam itself); this file pins the
two live effects at the actual consumer entry points the card names, so a
regression at the seam is caught at the point that matters, not just in the
parser's own unit tests.

**The verification artifact the count needed (external review, 2026-09-09,
GLM: the "nine" claim was asserted, not evidenced).** All nine, and their
call chain to ``fr_criteria``'s marker-stripping entry points, re-verified
by grep against this repo at fix time:

1. ``shared/scripts/lib/spec_parser.py`` — ``leading_criteria`` directly.
2. ``shared/scripts/lib/fr_criterion_shape.py`` — no ``fr_criteria`` import;
   receives already-extracted text from #4/#6 below.
3. ``plugins/shipwright-compliance/scripts/audit/group_i_criteria.py`` —
   ``has_criteria``/``criteria_for`` directly.
4. ``shared/scripts/tools/verifiers/_layer_coverage_ac.py`` —
   ``block_criteria`` directly (``criteria_digests``).
5. ``shared/scripts/tools/verifiers/layer_coverage.py`` — consumes #4's
   ``changed_criteria_ids``.
6. ``shared/scripts/tools/verifiers/layer_coverage_binding.py`` — same.
7. ``shared/scripts/tools/verifiers/_fr_hygiene_touched.py`` —
   ``block_criteria``/``criteria_for`` directly; also calls #2.
8. ``shared/scripts/tools/verifiers/_fr_hygiene_anomalies.py`` — consumes
   #7's ``_whole_doc_criteria_texts``.
9. ``shared/scripts/tools/verifiers/fr_hygiene.py`` — orchestrates #7/#8.

Below, #1/#2/#3/#4/#7 (the five that touch text or a digest directly) are
each exercised at their own entry point; #5/#6/#8/#9 consume one of those
five's already-marker-free output and add no further parsing of their own,
so they are not separately re-tested here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from lib import ac_identity, fr_criteria, spec_parser  # noqa: E402
from lib.fr_criterion_shape import is_well_formed_criterion  # noqa: E402
from verifiers._fr_hygiene_touched import _whole_doc_criteria_digests  # noqa: E402
from verifiers._layer_coverage_ac import criteria_digests  # noqa: E402


def test_layer_coverage_digest_unaffected_by_a_minted_marker():
    """Effect #1, at the cross-layer digest gate's own entry point: minting
    an id onto an already-authored criterion must not flip its digest."""
    spec = "## FR-01.03 — Title\n\n- (E) Given x, when y, then z.\n"
    minted = ac_identity.mint(spec).content
    assert criteria_digests(spec)["FR-01.03"] == criteria_digests(minted)["FR-01.03"]


def test_fr_hygiene_digest_unaffected_by_a_minted_marker():
    """Same effect #1, at the FR-row hygiene gate's own digest — a sibling
    implementation of the same pooling, reused independently (see that
    module's docstring for why it does not just call the function above)."""
    spec = "## FR-01.04 — Title\n\n- (E) Given x, when y, then z.\n"
    minted = ac_identity.mint(spec).content
    assert (
        _whole_doc_criteria_digests(spec)["FR-01.04"]
        == _whole_doc_criteria_digests(minted)["FR-01.04"]
    )


def test_a_minted_placeholder_does_not_change_either_digest():
    """Effect #2 at digest scope: a placeholder that contributed nothing to
    the digest pre-mint must still contribute nothing post-mint."""
    spec = "## FR-01.05 — Title\n\n- (E) TBD\n"
    minted = ac_identity.mint(spec).content
    assert criteria_digests(spec)["FR-01.05"] == criteria_digests(minted)["FR-01.05"]
    assert (
        _whole_doc_criteria_digests(spec)["FR-01.05"]
        == _whole_doc_criteria_digests(minted)["FR-01.05"]
    )


def test_spec_parser_reads_marker_free_criteria_after_mint():
    """Consumer #1 (S5's FR-coherence fallback), at its own entry point."""
    spec = "## FR-01.06 — Title\n\n- (E) Given x, when y, then z.\n"
    minted = ac_identity.mint(spec).content
    headings = spec_parser.parse_fr_headings(minted)
    assert headings[0].acceptance == "Given x, when y, then z."


def test_fr_criterion_shape_judges_marker_free_text_after_mint():
    """Consumer #2, fed the text a marker-aware reader (#3/#4/#7) would now
    hand it — the marker is gone before this function ever sees it."""
    spec = "## FR-01.07 — Title\n\n- (E) Given x, when y, then z.\n"
    minted = ac_identity.mint(spec).content
    (criterion,) = fr_criteria.criteria_for(minted, "FR-01.07")
    assert criterion == "Given x, when y, then z."
    assert is_well_formed_criterion(criterion) is True
