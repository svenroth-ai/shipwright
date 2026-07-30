"""The traceability matrix's deep links resolve to the catalog's anchors.

Split out of ``test_requirements_catalog_contract.py`` when that file reached the
300-line limit. The seam is the subject: the sibling owns what the CATALOG says
(ids, anchors, criterion shape, forbidden tokens); this owns the LINKAGE between
the generated matrix and that catalog. Nothing is imported across that seam — the
ids this file needs are read from the catalog's own anchors, so the two files
share a subject, not a constant.

**This is a real resolution, not an inspection.** It reads the generated matrix,
takes the link the matrix actually emits, resolves it relative to the matrix's own
directory, opens whatever that lands on, and checks the fragment is defined there.
A test that merely looked for ``<a id="fr-0101">`` in the catalog would pass just
as happily if the matrix had started emitting some other fragment.

Why explicit anchors at all: the matrix emits ``#fr-0101``, but the heading reads
``### FR-01.01 — /shipwright-run``, which github-slugger turns into
``fr-0101--shipwright-run``. The viewer matches anchors EXACTLY, so before campaign
S6 every one of these links scrolled nowhere and reported nothing.

@FR-01.10
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"
RTM = REPO_ROOT / ".shipwright" / "compliance" / "traceability-matrix.md"

_EXPLICIT_ANCHOR = re.compile(r'<a\s+id="([^"]+)"\s*>')
_RTM_FR_LINK = re.compile(r"\[(FR-[\d.]+)\]\(([^)]*spec\.md#[^)]+)\)")
_RTM_FR_ROW = re.compile(r"^\|\s*\[?(FR-\d+\.\d+)", re.M)


def _ids_the_catalog_defines() -> set[str]:
    """``{"FR-01.01", …}`` — from the catalog's ANCHORS, not from a constant.

    "An id the catalog does not define" is a statement about the catalog, so it is
    read from the catalog. The sibling file separately pins that this anchor set
    equals the expected id list, which keeps this file out of the business of
    knowing how many requirements there are.
    """
    anchors = _EXPLICIT_ANCHOR.findall(CATALOG.read_text(encoding="utf-8"))
    return {f"FR-{a[3:5]}.{a[5:]}" for a in anchors if re.fullmatch(r"fr-\d{4,}", a)}


@pytest.mark.skipif(not RTM.exists(), reason="traceability matrix not generated")
def test_every_rtm_deep_link_resolves_end_to_end():
    """END TO END: matrix → relative link → file on disk → anchor defined there.

    Every step is taken for real: the link text is read out of the generated matrix
    rather than reconstructed from the FR id, the path is resolved against the
    matrix's own directory the way a browser would, and the target file is opened
    rather than assumed to be the catalog.
    """
    matrix = RTM.read_text(encoding="utf-8")
    links = _RTM_FR_LINK.findall(matrix)
    linked = {fr for fr, _ in links}
    # Rows, not a count of the catalog's ids: #480 froze the matrix, so counting
    # against the catalog made minting a requirement unpassable. Both sides go empty
    # TOGETHER — a rowless matrix satisfies the equality — hence the floor above it.
    #
    # WHAT THIS STOPPED CATCHING, so the next reader does not assume otherwise. The
    # old form (`len(links) >= len(EXPECTED_IDS)`) also caught a requirement VANISHING
    # from the matrix; a dropped FR takes its row and its link together, so the
    # equality still holds and nothing here notices. That direction is unguarded
    # repo-wide, and reinstating it means reinstating the unpassable mint — the two
    # cannot both be had from this assertion.
    rows = set(_RTM_FR_ROW.findall(matrix))
    assert rows, "matrix emitted no FR rows — the generator read zero requirements"
    assert linked == rows, (f"rows without a link: {sorted(rows - linked)}; "
                            f"links without a row: {sorted(linked - rows)}")
    unknown = linked - _ids_the_catalog_defines()
    assert not unknown, f"matrix links ids the catalog does not define: {sorted(unknown)}"
    # EVERY link is resolved, not a representative one. A single spot-check would
    # meet the wording of the acceptance criterion while missing a mismatch
    # between the link generator's anchor convention and the catalog's ids.
    # NOT PROBED, because it does not exist here: a FOLDED row, whose slug
    # degrades worst of all (`fr-0107-folded--fr-0105-health-check`). This repo
    # has no `## FR-Fold-Map` and the matrix emits no folded link, so there is
    # nothing to resolve. The loop below would cover one the moment one appears.

    unresolved = []
    for fr_id, href in links:
        rel, _, fragment = href.partition("#")
        target = (RTM.parent / rel).resolve()
        if not target.is_file():
            unresolved.append(f"{fr_id}: {href} → no such file {target}")
            continue
        defined = set(_EXPLICIT_ANCHOR.findall(target.read_text(encoding="utf-8")))
        if fragment not in defined:
            unresolved.append(
                f"{fr_id}: #{fragment} is not defined in {target.name} "
                f"(a heading slug is NOT enough — the viewer matches exactly)"
            )
    assert not unresolved, "\n".join(unresolved)
