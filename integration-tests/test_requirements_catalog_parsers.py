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

#: The ids the catalog carries. S6 must not lose or renumber one; a later iterate
#: may append the next free number (FR-01.16 was minted 2026-07-23, REQ-3 Ph1;
#: FR-01.19 "Recovery of a broken shared branch" 2026-07-28,
#: iterate-2026-07-28-main-self-heal; FR-01.20 "Context-Cost Meter" 2026-08-07,
#: iterate-2026-08-07-context-cost-meter). The bound moves only by APPENDING — a
#: shorter tuple, or a changed id, is the loss this constant exists to catch.
EXPECTED_IDS = tuple(f"FR-01.{n:02d}" for n in range(1, 21))

#: ONE sys.path root for the whole module, so every shared module here is
#: reachable under exactly one identity (`lib.<name>`). Inserting both
#: `shared/scripts` and `shared/scripts/lib` would make each importable under
#: two names session-wide, and a module with two identities has two sets of
#: module-level state — ADR-045, and a defect class this campaign keeps finding.
_SHARED_SCRIPTS = str(REPO_ROOT / "shared" / "scripts")
if _SHARED_SCRIPTS not in sys.path:
    sys.path.insert(0, _SHARED_SCRIPTS)


def test_the_fr_table_reader_still_sees_every_requirement():
    """Counting table rows with a regex is not enough — read it as the AUDIT does.

    **Named for the ONE parser it covers, on purpose.** It was originally called
    ``..._the_production_parser_...``, and that singular was inaccurate: this
    repo has a second production parser over the same file
    (``spec_parser.parse_fr_headings``), and the name implied a coverage this
    test does not have. See ``test_the_heading_parser_sees_the_same_set``
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
        "Must", "Must", "Must", "May", "Must", "Must", "Must", "Must",
        "Must", "Should", "Should", "Should",
    ], (
        "priorities must survive the merge unchanged (FR-01.16/.17 = Must; "
        "FR-01.18 = Should — the pipeline is complete without the grader; "
        "FR-01.19 = Should — a change still ships when the shared branch is "
        "healthy, so recovering it is resilience rather than the core promise; "
        "FR-01.20 = Should — the meter adds a diagnostic figure, the pipeline "
        "already ran without it)"
    )


def test_the_heading_parser_sees_the_same_set():
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


def test_the_fr_heading_coherence_report_is_no_longer_wrong_here():
    """S5's coherence report about THIS catalog used to be false. Fixed in
    campaign REQ3.04, sub-iterate R0 (2026-08-25).

    ``compute_fr_coherence`` used to call a requirement "coherent" only when its
    heading was followed by ``**Description:**`` and ``**Acceptance Criteria:**``
    labelled blocks. This catalog states each requirement's description in the
    TABLE and its criteria as bare ``- (E) Given … when … then …`` bullets, so
    every one of them used to be reported as missing both — including the ones
    that had gained real criteria along the way. Pre-S6 the same file produced
    seven such entries; by the time R0 measured it, the merge had roughly
    DOUBLED that false statement, inside the campaign whose thesis is removing
    false statements.

    R0 is the fix this test used to say was "out of scope here": a shared
    criteria parser, ``lib.fr_criteria``, reads the shape the producers actually
    write (the same reader ``_layer_coverage_ac`` and Group I's I6 already used),
    and ``parse_fr_headings`` falls back to it when the labelled-form extraction
    finds nothing. Combined with the table-row exemption in
    ``compute_fr_coherence`` (a heading whose id is also a table row is a DETAIL
    section, not a definition, so its missing ``**Description:**`` label is not
    reported), every one of this catalog's twenty requirements now reads as
    fully coherent.

    This test used to assert the false count exactly, so that whoever fixed the
    shape or the check would be forced to update three records instead of
    leaving a stale one behind: this test, the "Known and deliberately not
    fixed here" section of the migration guide, and ADR-109's Honest limits.
    All three are updated in this diff. S1/S5 remain Tier-2 WARN and never
    touch an exit code — this test still pins the count, now the CORRECT one,
    so a future regression is caught the same way the original defect was.
    """
    # Scoped to the CATALOG, not the repo. ``compute_fr_coherence`` walks
    # `.shipwright/agent_docs/spec.md`, each `.shipwright/planning/<split>/spec.md`,
    # and — the one that matters here — every `.shipwright/planning/iterate/*.md`
    # (`spec_parser._iter_spec_files`). Asserting its repo-wide totals is NOT
    # done here for that reason: `.shipwright/planning/iterate/2026-07-23-
    # req3-phase2-FR-01.03-revisit-proposal.md` already carries a real, matching
    # `# FR-01.03`-shaped H1 heading (R0, 2026-08-25, verified directly against
    # `origin/main` — this is pre-existing, not a regression this diff
    # introduces) — see `test_compute_fr_coherence_resolves_every_catalog_requirement`
    # below for the catalog-scoped assertion that survives that unrelated file.
    from lib.spec_parser import parse_fr_headings  # noqa: PLC0415

    # 19 -> 20 on 2026-08-07 (iterate-2026-08-07-context-cost-meter): FR-01.20
    # was APPENDED to the catalog, in exactly the same shape as its nineteen
    # siblings — a detail section with criteria and no `**Description:**` label.
    # R0 (2026-08-25) taught the parser that shape, so the count below is the
    # number of requirements, not a count of false reports.
    headings = parse_fr_headings(CATALOG.read_text(encoding="utf-8"))
    assert len(headings) == 20
    missing_acceptance = [h.id for h in headings if not h.has_acceptance()]
    assert missing_acceptance == [], (
        "every heading in the catalog should now read a criterion via the "
        "lib.fr_criteria fallback — if this regresses, check that the bullets "
        "still sit directly under each ### FR-XX.YY heading (the adjacency "
        "rule requires no prose paragraph in between)."
    )
    # missing_both/missing_description need the table-row exemption, which
    # lives in `compute_fr_coherence`, not in `parse_fr_headings` itself — this
    # test only exercises the heading-level parser, so it asserts what THAT
    # parser can see: has_description() is still False for all twenty (no
    # `**Description:**` label; the description lives in the table cell,
    # which this narrower check never consults). See
    # `test_compute_fr_coherence_...` (shared/tests/test_spec_checks.py) and
    # this catalog's own coherence via `compute_fr_coherence` for the full
    # picture including the table-row exemption.
    missing_description = [h.id for h in headings if not h.has_description()]
    assert len(missing_description) == 20, (
        "the FR-coherence reading of THIS catalog changed again. If the "
        "catalog or the check was fixed, that is good — update this test, the "
        "note in docs/migrations/requirements-catalog-merge.md, and the "
        "Honest-limits entry in ADR-109 to match."
    )


def test_compute_fr_coherence_resolves_every_catalog_requirement():
    """The repo-wide FR-coherence WALK (not just the heading parser) reports
    every catalog requirement as coherent (external code review, 2026-08-25).

    Repo-wide ``report.ok`` is NOT asserted: one pre-existing, unrelated
    planning doc (see the comment above) already produces one ``missing_both``
    entry on ``origin/main``, before this diff — out of R0's scope. This test
    asserts what R0 actually changed: no CATALOG entry remains in any of the
    three gap buckets.
    """
    from lib.spec_parser import compute_fr_coherence  # noqa: PLC0415

    report = compute_fr_coherence(REPO_ROOT)
    catalog_rel = CATALOG.relative_to(REPO_ROOT).as_posix()
    for bucket_name, bucket in (
        ("missing_description", report.missing_description),
        ("missing_acceptance", report.missing_acceptance),
        ("missing_both", report.missing_both),
    ):
        catalog_entries = [e for e in bucket if e.startswith(f"{catalog_rel}::")]
        assert catalog_entries == [], (
            f"the catalog has {bucket_name} entries again: {catalog_entries}"
        )
