"""Drift protection for the two rules the REQ-3 granularity round settled.

Both rules are stated in more than one document by necessity — a rulebook the
plugins cite, and the generation template an author actually copies from — and
**the defect this round fixed was precisely those copies disagreeing**: the
template seeded `Basis: assumed` rows while the phase's own criterion forbade
them, so a reader following the template violated the rule they were following.
A guard that only checked the rulebook would not have caught it, because the
rulebook was never the file that was wrong.

So both directions are covered, per the registry-driven SSoT rule:

  forward — `fr-authoring.md` §3a exists and still states the granularity test;
            `requirement-elicitation.md` §8 still carries the qualified
            `assumed` rule;
  reverse — every doc that seeds or explains a `Basis` cell states the same
            qualification, and no generation template seeds a bare `assumed`
            row for a greenfield project.

Assertions are made on normalised text (whitespace collapsed, Markdown emphasis
stripped) and on substantive clauses rather than byte-equal prose, so reflowing
a paragraph does not fail the suite while a changed *rule* does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

FR_AUTHORING = REPO_ROOT / "shared" / "fr-authoring.md"
ELICITATION = REPO_ROOT / "shared" / "requirement-elicitation.md"
PROJECT_REFS = (
    REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project" / "references"
)
SPEC_GENERATION = PROJECT_REFS / "spec-generation.md"
SPLIT_HEURISTICS = PROJECT_REFS / "split-heuristics.md"

#: The vocabulary module's own docstring — a fourth copy of the `Basis` table,
#: and the one closest to the code that scores the cell.
FR_BASIS_MODULE = REPO_ROOT / "shared" / "scripts" / "lib" / "fr_basis.py"

#: The iterate surfaces that instruct an author to type a `Basis` cell. They
#: were the copies still licensing a bare `assumed` after the rulebooks were
#: corrected — found by grepping for the old gloss rather than by reasoning
#: about which files "should" have it, which is how a fifth copy hides.
ITERATE_REFS = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references"
)

#: Every surface that tells someone how to fill the cell. All of them must
#: state the qualification; a rule stated in five places and qualified in three
#: is the defect this round removed.
SETTLEMENT_SURFACES = (
    FR_AUTHORING,
    ELICITATION,
    SPEC_GENERATION,
    FR_BASIS_MODULE,
    ITERATE_REFS / "path-a-feature.md",
    ITERATE_REFS / "path-b-change.md",
)


def _norm(text: str) -> str:
    """Collapse whitespace and strip Markdown decoration for clause matching.

    Blockquote markers are stripped before the whitespace collapse: a rule
    stated inside a ``>`` callout — which both the granularity test and the
    split-heuristics pointer are — would otherwise normalise to
    ``"criteria that a > single delivery"`` and never match, failing the guard
    for a formatting choice rather than a changed rule.
    """
    text = text.replace("—", "-").replace("’", "'").replace("§", "")
    text = re.sub(r"^[ \t]*>[ \t]?", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*`_]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------------------------------------------------------------------------
# Forward — the rules are still stated where the citations point
# ---------------------------------------------------------------------------

def test_fr_authoring_carries_the_granularity_section():
    body = FR_AUTHORING.read_text(encoding="utf-8")
    assert "## 3a. How big is one requirement?" in body
    norm = _norm(body)
    # The test itself, not merely a heading.
    assert "acceptance criteria that a single delivery would satisfy" in norm
    assert "too broad" in norm and "divided" in norm
    # The signal that the judgement is owed.
    assert "unable to enumerate what would settle it" in norm


def test_granularity_section_keeps_the_judgement_human():
    """§3a must not read as though the check decides. I6 is a signal, not a verdict."""
    norm = _norm(FR_AUTHORING.read_text(encoding="utf-8"))
    assert "the judgement stays human" in norm
    assert "i6" in norm and "advisory" in norm


@pytest.mark.parametrize(
    "situation", ["shipwright-project", "shipwright-adopt"],
)
def test_every_situation_row_names_the_settlement(situation: str):
    """The §8 table rows must not disagree with the rule above them.

    Named by the external code review: the brownfield row licensed `assumed`
    on a bare "work item to confirm it", which names no confirmer and no
    experiment — the same shape of inconsistency (a rule stated one way and
    applied another) that this whole round exists to remove. Asserted per ROW,
    because a document-wide phrase search passes while one row still disagrees.
    """
    body = ELICITATION.read_text(encoding="utf-8")
    rows = [ln for ln in body.splitlines()
            if ln.startswith("|") and situation in ln]
    assert rows, f"no §8 situation row found for {situation}"
    norm = _norm(" ".join(rows))
    assert "who to ask" in norm or "what would settle it" in norm, (
        f"the {situation} row does not name what would settle an assumption"
    )


def test_elicitation_carries_the_qualified_assumed_rule():
    norm = _norm(ELICITATION.read_text(encoding="utf-8"))
    assert "assumed is never bare" in norm
    assert "what would settle it" in norm
    # The ban is on silent assuming, NOT on honest not-knowing — the distinction
    # the whole amendment turns on.
    assert "not on honest not-knowing" in norm or "never on honest not-knowing" in norm


# ---------------------------------------------------------------------------
# Reverse — the copies say the same thing
# ---------------------------------------------------------------------------

_BASIS_DOCS = pytest.mark.parametrize(
    "path", [FR_AUTHORING, ELICITATION, SPEC_GENERATION], ids=lambda p: p.name,
)


@pytest.mark.parametrize("path", SETTLEMENT_SURFACES, ids=lambda p: p.name)
def test_every_surface_qualifies_assumed(path: Path):
    """No surface may define `assumed` as bare "nobody confirmed this" any more.

    That bare gloss is what licensed the template rows this round removed, and
    it survived in three further copies (the vocabulary module's own docstring
    and both iterate path references) after the rulebooks were corrected. Every
    place that tells an author how to fill the cell is pinned, because the
    failure mode is not "the rule is wrong" but "one copy of it is stale".
    """
    assert path.exists(), f"{path} has moved — update this guard"
    norm = _norm(path.read_text(encoding="utf-8"))
    assert "what would settle it" in norm, f"{path.name} does not qualify `assumed`"


@_BASIS_DOCS
def test_every_basis_doc_sends_the_settlement_to_a_criterion(path: Path):
    """The settlement goes in an acceptance criterion, never the Basis cell.

    A qualified cell (`assumed - ask the PO`) is malformed and fails audit I5,
    so a doc telling an author to write it there would produce a failing spec.
    """
    norm = _norm(path.read_text(encoding="utf-8"))
    assert "i5" in norm, f"{path.name} does not warn that a qualified cell fails I5"
    assert "acceptance criterion" in norm or "acceptance criteria" in norm


def test_generation_template_seeds_no_bare_assumed_row():
    """The exact contradiction this round fixed, pinned so it cannot return.

    A template row reading `| ... | assumed | ... |` is what a greenfield author
    copies; the phase's own criterion forbids exactly that. Rows are checked, not
    prose — the file legitimately discusses `assumed` at length.
    """
    offenders = [
        line.strip()
        for line in SPEC_GENERATION.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("|") and re.search(r"\|\s*assumed\s*\|", line)
    ]
    # The one worked example demonstrating the qualified form is allowed, and is
    # the row whose settlement criterion the round added.
    assert len(offenders) <= 1, f"template seeds bare `assumed` rows: {offenders}"
    if offenders:
        assert "FR-01.05" in offenders[0], (
            "the only `assumed` row must be the worked example carrying a "
            f"settlement criterion, got: {offenders[0]}"
        )


def test_worked_example_assumed_row_has_its_settlement_criterion():
    """The demonstrated `assumed` row must actually demonstrate the rule."""
    norm = _norm(SPEC_GENERATION.read_text(encoding="utf-8"))
    assert "confirm the threshold with the product owner" in norm


# ---------------------------------------------------------------------------
# Reverse — the granularity rule is cited where authors read
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path", [SPEC_GENERATION, SPLIT_HEURISTICS, ELICITATION], ids=lambda p: p.name,
)
def test_granularity_rule_is_cited(path: Path):
    norm = _norm(path.read_text(encoding="utf-8"))
    assert "fr-authoring.md 3a" in norm, (
        f"{path.name} does not cite the granularity rule"
    )


def test_split_heuristics_distinguishes_the_two_granularities():
    """The two sizings must not be readable as one.

    `split-heuristics.md` sizes the planning unit; §3a sizes the requirement.
    Conflating them is what left requirement granularity unguided while planning
    granularity looked covered.
    """
    norm = _norm(SPLIT_HEURISTICS.read_text(encoding="utf-8"))
    assert "sizes the planning unit, not the requirement" in norm
