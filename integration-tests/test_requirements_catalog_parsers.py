"""Which parsers read the requirements catalog, and what each of them sees.

Split out of ``test_requirements_catalog_contract.py`` (campaign S6) once that
module crossed its size guideline. The seam is real rather than convenient: the
sibling module asserts properties of the catalog as a DOCUMENT — its ids, its
anchors, its links, what its prose may not contain. This one asserts what the
code that READS the document makes of it, which is a different question with a
different failure mode.

S6 is why the question exists. Giving every requirement a ``### FR-01.NN``
heading, so each deep link has somewhere to land, created a second textual
occurrence of every id — and this repo has two production parsers over the same
file that disagree about what a requirement is. Neither disagreement is a bug on
its own; both being invisible would be.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"

#: The ids the catalog carried before the merge. S6 must not lose or renumber one.
EXPECTED_IDS = tuple(f"FR-01.{n:02d}" for n in range(1, 16))

#: ONE sys.path root for the whole module, so every shared module here is
#: reachable under exactly one identity (`lib.<name>`). Inserting both
#: `shared/scripts` and `shared/scripts/lib` would make each importable under
#: two names session-wide, and a module with two identities has two sets of
#: module-level state — ADR-045, and a defect class this campaign keeps finding.
_SHARED_SCRIPTS = str(REPO_ROOT / "shared" / "scripts")
if _SHARED_SCRIPTS not in sys.path:
    sys.path.insert(0, _SHARED_SCRIPTS)


def test_the_fr_table_reader_still_sees_exactly_fifteen_requirements():
    """Counting table rows with a regex is not enough — read it as the AUDIT does.

    **Named for the ONE parser it covers, on purpose.** It was originally called
    ``..._the_production_parser_...``, and that singular was inaccurate: this
    repo has a second production parser over the same file
    (``spec_parser.parse_fr_headings``), and the name implied a coverage this
    test does not have. See ``test_the_heading_parser_sees_the_same_fifteen``
    and ``test_the_fr_heading_coherence_report_is_knowingly_wrong_here`` below.

    S6 gave every requirement a ``### FR-01.NN`` section so each has an anchor to
    land on. That creates a SECOND textual occurrence of every id, and the failure
    mode it opens is precise: a reader that treated headings as rows would report
    thirty requirements, or fifteen duplicates, and the global I4 duplicate check
    would fail the audit on a catalog that is in fact correct. A regex counting
    table rows would not notice, because the table would still be right.

    Raised in external review of this step; the risk was real and unpinned.
    """
    from lib.fr_table_reader import read_fr_rows  # noqa: PLC0415

    rows = read_fr_rows(CATALOG.read_text(encoding="utf-8"))
    assert tuple(r.id for r in rows) == EXPECTED_IDS
    assert all(r.status == "active" for r in rows)
    assert [r.priority for r in rows] == [
        "Must", "Must", "Must", "Should", "Must", "Must", "Must", "Should",
        "Must", "Must", "Must", "May", "Must", "Must", "Must",
    ], "priorities must survive the merge unchanged"


def test_the_heading_parser_sees_the_same_fifteen():
    """The SECOND production parser over this file — the one the name above hid.

    ``spec_parser.parse_fr_headings`` matches ``### FR-01.01 — /shipwright-run``
    and feeds the S1 / S5 spec checks. S6 created fifteen such headings where
    there had been seven, so this file now has two parsers reading it with two
    different notions of what a requirement is. Both are pinned here, because
    "the production parser" is not a thing that exists.

    Agreement on the ID SET is the property that matters: whatever else the two
    disagree about, a requirement must not appear to one and not the other.
    """
    from lib.spec_parser import parse_fr_headings  # noqa: PLC0415

    headings = parse_fr_headings(CATALOG.read_text(encoding="utf-8"))
    assert tuple(h.id for h in headings) == EXPECTED_IDS


def test_the_fr_heading_coherence_report_is_knowingly_wrong_here():
    """S5's coherence report about THIS catalog is false, and that is recorded.

    ``compute_fr_coherence`` calls a requirement "coherent" when its heading is
    followed by ``**Description:**`` and ``**Acceptance Criteria:**`` labelled
    blocks. The catalog states each requirement's description in the TABLE and
    its criteria as ``- (E) Given … when … then …`` bullets, so all fifteen are
    reported as missing both — including the eight that gained real criteria in
    this very step. Pre-S6 the same file produced seven such entries, so the
    merge roughly DOUBLED a false statement, inside the campaign whose thesis is
    removing false statements.

    Three options were weighed and the first two rejected:

    * **Add the labels** — needs ``**Description:**`` per section, duplicating
      the table cell fifteen times. Two copies of one sentence that drift apart
      is precisely what this campaign removes.
    * **Rename the headings** so the parser stops matching — degrades the human
      document to dodge a parser, and the deep links land on those headings.
    * **Teach the check that a heading whose id is also a table row is a DETAIL
      section, not a definition** — the correct fix, and out of scope here:
      ``spec_parser`` is a shared verifier every adopted repo consumes, and this
      is a migration PR with no baseline for that behaviour change.

    So the wrongness ships, deliberately, and is recorded in three places rather
    than left to be rediscovered: here, the "Known and deliberately not fixed
    here" section of the migration guide, and ADR-109's Honest limits. S1/S5 are
    Tier-2 WARN and never touch an exit code, so nothing is gated on it. **The
    count is asserted exactly**: when someone fixes the shape or the check, this
    test fails and forces all three records to be updated instead of the false
    report quietly persisting.
    """
    # Scoped to the CATALOG, not the repo. ``compute_fr_coherence`` walks
    # `.shipwright/agent_docs/spec.md`, each `.shipwright/planning/<split>/spec.md`,
    # and — the one that matters here — every `.shipwright/planning/iterate/*.md`
    # (`spec_parser._iter_spec_files`). So asserting its repo-wide totals would
    # break the day any iterate document grows an `### FR-01.03`-shaped heading,
    # with a message blaming the catalog or the check. It holds today only
    # because the sole FR-ish heading in that tree is `## FR-Fold-Map`, which the
    # heading regex does not match — luck, not scope. The same production reader
    # is used, just pointed at one file.
    from lib.spec_parser import parse_fr_headings  # noqa: PLC0415

    headings = parse_fr_headings(CATALOG.read_text(encoding="utf-8"))
    assert len(headings) == 15
    missing_both = [h.id for h in headings
                    if not h.has_description() and not h.has_acceptance()]
    assert len(missing_both) == 15, (
        "the FR-coherence reading of THIS catalog changed. If the catalog or the "
        "check was fixed, that is good — update this test, the note in "
        "docs/migrations/requirements-catalog-merge.md, and the Honest-limits "
        "entry in ADR-109 to match."
    )
