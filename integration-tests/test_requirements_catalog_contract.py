"""The contract the merged requirements catalog owes its consumers (campaign S6).

S6 merged the requirements into ONE catalog at the path they already occupied,
compacted the per-change prose out of them, and started emitting deep-link
anchors explicitly. Each of those three has a way of failing silently, so each
gets an assertion here rather than a promise in a commit message.

**The anchor assertion is a real resolution, not an inspection.** It reads the
generated traceability matrix, takes the link the matrix actually emits, resolves
it relative to the matrix's own directory, opens whatever that lands on, and
checks the fragment is defined there. A test that merely looked for
``<a id="fr-0101">`` in the catalog would pass just as happily if the matrix had
started emitting some other fragment.

Why explicit anchors at all: the matrix emits ``#fr-0101``, but the heading reads
``### FR-01.01 — /shipwright-run``, which github-slugger turns into
``fr-0101--shipwright-run``. The viewer matches anchors EXACTLY, so before S6
every one of these links scrolled nowhere and reported nothing.

@FR-01.10
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"
RTM = REPO_ROOT / ".shipwright" / "compliance" / "traceability-matrix.md"

#: The ids the catalog carries. S6 must not lose or renumber one; a later iterate
#: may append the next free number (FR-01.16 was minted 2026-07-23, REQ-3 Ph1).
EXPECTED_IDS = tuple(f"FR-01.{n:02d}" for n in range(1, 17))

_EXPLICIT_ANCHOR = re.compile(r'<a\s+id="([^"]+)"\s*>')
_RTM_FR_LINK = re.compile(r"\[(FR-[\d.]+)\]\(([^)]*spec\.md#[^)]+)\)")
_TABLE_ROW = re.compile(r"^\|\s*(FR-\d+\.\d+)\s*\|")
_CRITERION = re.compile(r"^\s*-\s+\(E\)\s")

#: What a requirement sentence must not carry (`shared/fr-authoring.md`, and the
#: S6 acceptance criterion). Each is a thing that rots: a run id and a decision
#: number point at a record that moves, a path points at a file that gets renamed.
_FORBIDDEN = {
    "run id": re.compile(r"\biterate-\d{4}"),
    "decision-record number": re.compile(r"\bADR-\d+"),
    "path-like token": re.compile(r"(?<![\w-])[\w.-]+/[\w./-]+"),
    "source filename": re.compile(
        r"\b[\w-]+\.(?:py|md|json|jsonl|ts|tsx|js|yml|yaml|sh|toml|cfg|ini)\b"
    ),
}


@pytest.fixture(scope="module")
def catalog() -> str:
    return CATALOG.read_text(encoding="utf-8")


def _requirement_text(text: str) -> list[tuple[str, str]]:
    """(where, sentence) for every piece of REQUIREMENT prose in the catalog.

    That is the table's Description cell plus every ``- (E) …`` criterion — not
    the surrounding narration, and not the "where the work detail lives"
    pointers, which are navigation by design (S6 scope: planning documents keep
    the work detail and are LINKED from the catalog).
    """
    out: list[tuple[str, str]] = []
    current = "?"
    for line in text.splitlines():
        row = _TABLE_ROW.match(line)
        if row:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # | ID | Area | Name | Priority | Description | Basis | Layers |
            out.append((f"{row.group(1)} description", cells[4]))
            continue
        heading = re.match(r"^###\s+(FR-\d+\.\d+)\b", line)
        if heading:
            current = heading.group(1)
        elif _CRITERION.match(line):
            out.append((f"{current} criterion", line.strip()))
    return out


def test_all_requirements_survive_with_unchanged_ids(catalog):
    """The merge is a merge, not a rewrite: no original id lost or renumbered.
    New ids are only ever appended at the next free number (FR-01.16, REQ-3)."""
    found = tuple(m.group(1) for m in
                  (_TABLE_ROW.match(ln) for ln in catalog.splitlines()) if m)
    assert found == EXPECTED_IDS


def test_the_catalog_path_is_covered_by_a_registered_artifact_migration():
    """The step's acceptance criterion, resolved rather than waived.

    The criterion reads "the path is registered in ``artifact_migrations.py`` so
    ``test_artifact_path_canon`` passes", written in anticipation of the catalog
    quoting legacy-looking paths and needing an ALLOWLIST exemption. It does not
    quote any — the compaction removed them — so no exemption was added: granting
    one would license exactly what this step forbids.

    What the criterion is actually asking for is nonetheless true, and this is
    where that is checked rather than argued in a commit message: the catalog
    lives under ``.shipwright/planning``, which IS a registered migration, and its
    status is ``migrated`` (the drift detector treats it as a hard gate). A
    passing lint alone would not establish that — a lint can pass by coincidence.
    """
    # Imported under the `lib.` package identity, NOT by inserting
    # `shared/scripts/lib` as a second sys.path root. Both roots would leave
    # this module importable under two names for the rest of the session
    # (ADR-045), and a module with two identities has two sets of module-level
    # state -- which is exactly the class of defect this campaign keeps finding.
    from lib.artifact_migrations import active_migrations, get_migration  # noqa: PLC0415

    # The argument below is a MIGRATION NAME being looked up, not a path
    # reference — marked inline rather than widening the lint's allowlist to
    # cover all of integration-tests/, which would exempt files that really
    # could carry a legacy path.
    planning = get_migration("planning")  # artifact-path-canon: legacy
    assert planning is not None, "the planning migration must stay registered"
    assert planning["status"] == "migrated"
    assert planning in active_migrations(), "must remain under drift detection"

    rel = CATALOG.relative_to(REPO_ROOT).as_posix()
    assert rel.startswith(planning["canonical"] + "/"), (
        f"the catalog moved out from under the registered migration: {rel}"
    )
    assert rel == ".shipwright/planning/01-adopted/spec.md", (
        "the catalog must NOT move. A requirements file directly under "
        ".shipwright/planning/ is invisible to every directory walk in the "
        "toolchain, which reads as zero requirements, which reads as pass or "
        "skip nearly everywhere — the requirements checks go dark while "
        "reporting green, and every feature change simultaneously fails "
        "finalization."
    )


def test_every_requirement_has_an_explicit_anchor(catalog):
    """One anchor per requirement, defined ONCE.

    Uniqueness is load-bearing rather than tidy: the consumer resolves a fragment
    against an exact set, so a duplicated id makes the destination arbitrary.
    """
    anchors = _EXPLICIT_ANCHOR.findall(catalog)
    fr_anchors = [a for a in anchors if a.startswith("fr-")]
    assert fr_anchors == [f"fr-01{n:02d}" for n in range(1, 17)]
    assert len(set(anchors)) == len(anchors), "duplicate anchor id"


@pytest.mark.skipif(not RTM.exists(), reason="traceability matrix not generated")
def test_every_rtm_deep_link_resolves_end_to_end():
    """END TO END: matrix → relative link → file on disk → anchor defined there.

    Every step is taken for real. The link text is not reconstructed from the FR
    id, it is read out of the generated matrix; the path is resolved against the
    matrix's own directory the way a reader's browser would; and the target file
    is opened rather than assumed to be the catalog.
    """
    links = _RTM_FR_LINK.findall(RTM.read_text(encoding="utf-8"))
    assert len(links) >= len(EXPECTED_IDS), "matrix emitted no FR deep links"
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


def test_no_requirement_text_carries_a_run_id_adr_number_or_path(catalog):
    """S6 acceptance criterion, checked rather than asserted.

    These are the three things that make a requirement rot: they name a record,
    a decision or a file that moves independently of the capability. The work
    detail they used to point at is reachable from the event log and the planning
    tree instead — see the catalog's closing section.
    """
    offenders = [
        f"{where}: {label} → {hit.group(0)!r}"
        for where, sentence in _requirement_text(catalog)
        for label, pattern in _FORBIDDEN.items()
        if (hit := pattern.search(sentence))
    ]
    assert not offenders, "\n".join(offenders)


def test_the_catalog_declares_no_removed_requirements_section(catalog):
    """Nothing has ever been removed from this spec, so no such section exists.

    Pinned because it is easy to "restore" one out of a sense of completeness,
    and the removal-coverage gate reads that section as a claim that requirements
    WERE retired — which would then demand coverage evidence for retirements that
    never happened. S4 established the same fact from the other direction: the
    one inline ``**REMOVED** by`` marker this repo carried retired a
    sub-behaviour, not a requirement, and S6 folded it into FR-01.01's criteria.
    """
    assert not re.search(r"^#{2,3}\s+Removed Requirements\s*$", catalog, re.M)


def test_every_layers_cell_keeps_the_inferred_marker(catalog):
    """Layers stay NON-authoritative through the merge.

    A ``Layers`` cell without the literal ``(inferred)`` marker flips that
    requirement's provenance to ``explicit``, which routes any coverage gap to a
    hard ERROR. Most of the requirements have no test links at all, so dropping
    the marker while rewriting the table would hard-block the campaign on gaps
    nobody introduced. Narrow regex on purpose: ``unit, e2e (auto)`` does not
    match and would yield ``explicit``.
    """
    cells = [
        [c.strip() for c in line.strip().strip("|").split("|")][6]
        for line in catalog.splitlines() if _TABLE_ROW.match(line)
    ]
    assert len(cells) == len(EXPECTED_IDS)
    assert all(re.search(r"\(\s*inferred\s*\)", c, re.I) for c in cells)
