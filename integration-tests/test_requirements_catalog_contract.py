"""The contract the merged requirements catalog owes its consumers (campaign S6).

S6 merged the requirements into ONE catalog at the path they already occupied,
compacted the per-change prose out of them, and started emitting deep-link
anchors explicitly. Each of those three has a way of failing silently, so each
gets an assertion here rather than a promise in a commit message.

Scope is the CATALOG: which ids it carries, that each has a unique explicit
anchor, that its criteria are assertion-shaped, and that its prose carries none
of the tokens that rot. Whether the generated traceability matrix's deep links
actually RESOLVE to those anchors is the neighbouring subject and lives in
``test_rtm_deep_links.py``, split out when this file reached the 300-line limit.

@FR-01.10
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"

#: The ids the catalog carries. S6 must not lose or renumber one; a later iterate may
#: append the next free number (FR-01.16 minted 2026-07-23 REQ-3 Ph1; FR-01.19 2026-07-28
#: iterate-2026-07-28-main-self-heal; FR-01.20 2026-08-07 iterate-2026-08-07-context-
#: cost-meter). The bound moves only by APPENDING — a diff that makes this tuple
#: shorter, or changes an id in it, is the loss this constant exists to catch, and the
#: number must NOT be adjusted to match.
EXPECTED_IDS = tuple(f"FR-01.{n:02d}" for n in range(1, 21))

_EXPLICIT_ANCHOR = re.compile(r'<a\s+id="([^"]+)"\s*>')
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
    New ids are only ever appended at the next free number (FR-01.16, FR-01.17
    and FR-01.18, all REQ-3)."""
    found = tuple(m.group(1) for m in
                  (_TABLE_ROW.match(ln) for ln in catalog.splitlines()) if m)
    assert found == EXPECTED_IDS


def _criteria_sentences(text: str) -> list[tuple[str, str]]:
    """(FR-id, full criterion) with continuation lines joined.

    ``_requirement_text`` deliberately yields ONE line per criterion — enough for
    the forbidden-token scan, which is a per-token check. A shape check is not:
    the clause it looks for routinely sits on the second or third line, so
    reading line-by-line would flag almost every criterion in the catalog.
    """
    out: list[tuple[str, str]] = []
    current = "?"
    buf: list[str] | None = None
    for line in text.splitlines():
        heading = re.match(r"^###\s+(FR-\d+\.\d+)\b", line)
        if heading:
            current = heading.group(1)
        if _CRITERION.match(line):
            if buf:
                out.append((buf[0], buf[1]))
            buf = [current, line.strip()]
        elif buf is not None and line.startswith("  ") and line.strip():
            buf[1] += " " + line.strip()
        elif buf is not None:
            out.append((buf[0], buf[1]))
            buf = None
    if buf:
        out.append((buf[0], buf[1]))
    return out


def test_every_criterion_is_assertion_shaped(catalog):
    """`- (E) Given ... when ... then ...` — the `when` clause is not optional.

    `fr-authoring.md` states the shape and nothing checked it. An external
    review of the REQ-3 Phase-2 head found four criteria written
    `Given ... then ...`, with no observable trigger between the precondition
    and the promise — one in `.02`, two in `.04`, one in `.08`, all inherited
    from earlier walks. A criterion with no trigger cannot say *when* it must
    hold, which is the half a test binds to.

    Pinned here rather than left to the next reader, because the finding came
    from a model reading prose: a mechanical shape is exactly the thing that
    should never need one.
    """
    missing = [
        (fr, sentence[:70])
        for fr, sentence in _criteria_sentences(catalog)
        if not re.search(r"\bwhen\b", sentence, re.IGNORECASE)
    ]
    assert missing == [], (
        f"criteria without a `when` clause (not assertion-shaped): {missing}"
    )


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
    # Derived from EXPECTED_IDS rather than repeating its bound: the two were
    # separate literals, so appending FR-01.19 moved one and left this one
    # behind. One source, one place to append.
    assert fr_anchors == [i.replace("FR-", "fr-").replace(".", "")
                          for i in EXPECTED_IDS]
    assert len(set(anchors)) == len(anchors), "duplicate anchor id"


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
