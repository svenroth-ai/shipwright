"""The ``Basis`` vocabulary that replaced ``Source`` (SPEC §3.2, decision D3).

Severity is the point of these tests: a value outside the vocabulary is a typo
and must be hard; ``other`` is a real special case and must never block. Getting
that backwards in either direction breaks the column — a blocking ``other`` is
not an escape hatch, and a passing typo is not a vocabulary.

@FR-01.02
@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "lib"))

from fr_basis import BASIS_VALUES, BASIS_VOCABULARY, classify  # noqa: E402


def test_the_vocabulary_is_the_one_the_campaign_decided() -> None:
    assert BASIS_VALUES == ("interview", "code", "observed", "tests", "assumed")
    assert BASIS_VOCABULARY == (*BASIS_VALUES, "other")


@pytest.mark.parametrize("value", BASIS_VALUES)
def test_every_vocabulary_value_is_known_and_never_blocks(value: str) -> None:
    verdict = classify(value)
    assert verdict.kind == "known"
    assert verdict.value == value
    assert verdict.blocking is False


@pytest.mark.parametrize("cell", ["Code", "  code  ", "`code`", "**code**"])
def test_case_whitespace_and_markdown_emphasis_are_tolerated(cell: str) -> None:
    """A human typing into a Markdown table should not lose on presentation."""
    assert classify(cell).kind == "known"
    assert classify(cell).value == "code"


def test_a_value_outside_the_vocabulary_is_hard() -> None:
    """That is a typo, and a typo is not a special case (SPEC §3.2)."""
    verdict = classify("enrichment.json")
    assert verdict.kind == "malformed"
    assert verdict.blocking is True
    assert "not in the vocabulary" in verdict.note


@pytest.mark.parametrize("cell,reason", [
    ("other: legacy import", "legacy import"),
    ("other — legacy import", "legacy import"),
    ("other - legacy import", "legacy import"),
    ("other (crawl only)", "crawl only"),
])
def test_other_carries_its_reason_whatever_separator_was_used(cell: str, reason: str) -> None:
    """Generous on separators: rejecting a well-meant reason over a dash-vs-colon
    choice pushes authors back to the bare form, losing the text we asked for."""
    verdict = classify(cell)
    assert verdict.kind == "other"
    assert verdict.reason == reason
    assert verdict.blocking is False


def test_a_bare_other_is_advisory_not_malformed() -> None:
    """SPEC §3.2 defines the hard class as "neither in the vocabulary nor
    ``other``". A missing reason does not move a value out of the vocabulary, so
    it is nagged in the note rather than escalated to a gate."""
    verdict = classify("other")
    assert verdict.kind == "other"
    assert verdict.blocking is False
    assert verdict.note == "no reason given"


def test_a_word_merely_starting_with_other_is_not_other() -> None:
    """`otherwise` is a typo, not the escape hatch — the boundary is a word one."""
    assert classify("otherwise").kind == "malformed"


def test_an_empty_cell_is_empty_not_malformed() -> None:
    """Every pre-S5 spec is in this state; hard-failing it would make adopting
    the column a breaking change for every existing repo."""
    for cell in ("", "   "):
        verdict = classify(cell)
        assert verdict.kind == "empty"
        assert verdict.blocking is False


@pytest.mark.parametrize("cell", ["code (enrichment.json)", "observed - staging", "tests: unit"])
def test_a_known_value_with_a_qualifier_is_hard_but_says_why(cell: str) -> None:
    """Still hard — letting `code (…)` through re-opens the door D3 closed, since
    the qualifier authors reach for first is the file path `Basis` replaced. But
    "not in the vocabulary" is useless advice to someone who used a vocabulary
    word, so this case names what is actually wrong."""
    verdict = classify(cell)
    assert verdict.blocking is True
    assert "takes no qualifier" in verdict.note
