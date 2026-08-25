"""The I6 criteria parser — does a requirement carry acceptance criteria at all?

Shape and boundary tests over pure string fixtures. The producer round-trips and
the per-file matching rule live in ``test_group_i_criteria_roundtrip.py``; the
finding wiring lives in ``test_audit_group_i_criteria.py``.

**Why this parser exists rather than a reuse of S5.** ``spec_parser`` (which
backs ``check_s5_fr_coherence``) only recognises FR bodies introduced by a
``**Acceptance Criteria:**`` bold label. The converged shape that
``/shipwright-project`` and ``/shipwright-adopt`` actually emit uses
``### FR-XX.YY — Title`` headings with bare bullets, so S5 reports every FR in
this repo's own 19-requirement catalogue as "missing acceptance" while each one
is fully elaborated. A check meant to warn about *zero* criteria has to read the
shape the producers write.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit.group_i_criteria import criteria_for, has_criteria  # noqa: E402


# ---------------------------------------------------------------------------
# Shape 1 — heading form (adopt, and this repo's own catalogue)
# ---------------------------------------------------------------------------

_HEADING_FORM = """\
## Acceptance Criteria

<a id="fr-0101"></a>
### FR-01.01 — /shipwright-run

- (E) Given a described change, when the pipeline is run, then the phases
  execute in order.
- (E) Given a phase fails, when the run continues, then it stops.

### FR-01.02 — /shipwright-project

_TBD — refine via /shipwright-iterate._
"""


def test_heading_form_counts():
    assert has_criteria(_HEADING_FORM, "FR-01.01") is True


def test_tbd_placeholder_is_no_criteria():
    """The exact state seven rows sat in from May until the REQ-3 campaign."""
    assert has_criteria(_HEADING_FORM, "FR-01.02") is False


def test_missing_block_reported():
    assert has_criteria(_HEADING_FORM, "FR-01.09") is False


# ---------------------------------------------------------------------------
# Shape 2 — bold-label form (the /shipwright-project template)
# ---------------------------------------------------------------------------

_BOLD_FORM = """\
### Acceptance Criteria

**FR-01.01: User Registration**
- [ ] User can register with valid email and password (min 8 chars)
- [ ] Duplicate email returns clear error message

**FR-01.02: User Login**
- [ ] TBD
"""


def test_bold_label_form_counts():
    assert has_criteria(_BOLD_FORM, "FR-01.01") is True


def test_bold_label_placeholder_is_no_criteria():
    """A checkbox whose only content is a placeholder is not a criterion."""
    assert has_criteria(_BOLD_FORM, "FR-01.02") is False


# ---------------------------------------------------------------------------
# Boundaries — the cases the external plan review named
# ---------------------------------------------------------------------------

def test_table_row_is_not_an_anchor():
    """An FR table row must never satisfy its own criteria requirement.

    Every spec states each FR id in the requirements table. If a `| FR-.. |`
    row counted as an anchor, the pipe-delimited cells after it would read as
    content and every requirement would trivially "have criteria" — the check
    would pass on exactly the specs it exists to flag.
    """
    table_only = """\
## Functional Requirements

| ID | Name | Priority | Description | Basis | Layers |
|---|---|---|---|---|---|
| FR-01.01 | Login | Must | The system SHALL authenticate a user. | interview | unit |
"""
    assert has_criteria(table_only, "FR-01.01") is False


def test_block_ends_at_eof():
    """A requirement last in the file has no following anchor to stop at."""
    at_eof = """\
### FR-03.07 — Last requirement in the document

- (E) Given the file ends here, when parsed, then the criteria still count.
"""
    assert has_criteria(at_eof, "FR-03.07") is True


def test_sibling_heading_does_not_donate_criteria():
    """Bullets under a NON-FR sibling heading belong to that heading, not the FR."""
    donated = """\
### FR-04.01 — A requirement with no criteria of its own

### Notes

- this bullet belongs to Notes, not to FR-04.01
"""
    assert has_criteria(donated, "FR-04.01") is False


def test_deeper_subheading_stays_inside_the_block():
    """A lower-level heading is part of the FR's block, not a terminator."""
    nested = """\
### FR-04.02 — A requirement whose criteria sit under a subheading

#### Acceptance criteria

- (E) Given a nested heading, when parsed, then these still count.
"""
    assert has_criteria(nested, "FR-04.02") is True


def test_legacy_bold_acceptance_label_still_counts():
    """The `**Acceptance Criteria:**` shape `spec_parser` knows is not excluded.

    No special-case branch handles this: the label sits INSIDE the FR's block,
    so the bullets under it are collected like any others. The test pins that
    the general rule covers the legacy shape.
    """
    legacy = """\
## FR-02.03 — Legacy shape

**Description:** what it does.

**Acceptance Criteria:**
- the criterion
"""
    assert has_criteria(legacy, "FR-02.03") is True


def test_id_match_is_boundary_anchored():
    """`FR-01.02` must not be satisfied by a block belonging to `FR-01.029`."""
    neighbour = """\
### FR-01.029 — A different requirement

- (E) Given a longer id, when parsed, then it does not satisfy the shorter one.
"""
    assert has_criteria(neighbour, "FR-01.02") is False
    assert has_criteria(neighbour, "FR-01.029") is True


def test_placeholder_variants_are_not_criteria():
    for placeholder in ("- TBD", "- TODO", "- [ ] TBA", "- [ ]", "- tbd.", "- N/A"):
        block = f"### FR-05.01 — Placeholder\n\n{placeholder}\n"
        assert has_criteria(block, "FR-05.01") is False, placeholder


def test_heading_merely_mentioning_the_id_is_not_an_anchor():
    """A heading that TALKS ABOUT an FR must not supply its criteria.

    Named by the external code review, and the worst failure direction for this
    check: a discussion or cross-reference heading (`### Notes for FR-01.01`,
    `### Migration away from FR-01.01`) carrying any bullet would suppress the
    warning for a requirement that has no criteria block at all — a false green
    in the check built to catch exactly that.
    """
    discussion = """\
### Notes for FR-06.01

- some background remark that is not an acceptance criterion
"""
    assert has_criteria(discussion, "FR-06.01") is False


def test_anchor_accepts_the_shapes_producers_emit():
    """The tightened anchor must still admit every real heading form."""
    for heading in (
        "### FR-06.02 — With an em dash",
        "### FR-06.02 - With a hyphen",
        "### FR-06.02: With a colon",
        "## FR-06.02",
        "#### FR-06.02 Plain title",
    ):
        block = f"{heading}\n\n- (E) Given ... then ...\n"
        assert has_criteria(block, "FR-06.02") is True, heading


def test_real_criterion_alongside_a_placeholder_counts():
    block = """\
### FR-05.02 — Mixed

- TBD
- (E) Given a real criterion, when parsed, then the block is not empty.
"""
    assert has_criteria(block, "FR-05.02") is True


# ---------------------------------------------------------------------------
# criteria_for — I6's own entry point for the LIST, not just has_criteria's
# boolean (doubt-review round 1, 2026-08-25, trg-467b7b2f). The convergence
# test in integration-tests/ calls this same function via a subprocess bridge
# (ADR-044); this in-process call is what gives it direct diff coverage.
# ---------------------------------------------------------------------------

def test_criteria_for_returns_the_criteria_list():
    first = (
        "Given a described change, when the pipeline is run, then the phases "
        "execute in order."
    )
    second = "Given a phase fails, when the run continues, then it stops."
    assert criteria_for(_HEADING_FORM, "FR-01.01") == [first, second]


def test_criteria_for_is_empty_when_there_is_no_block():
    assert criteria_for(_HEADING_FORM, "FR-01.09") == []
