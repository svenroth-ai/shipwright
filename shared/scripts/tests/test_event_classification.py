"""Tests for shared/scripts/event_classification.py :: normalize_intent."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_classification import normalize_intent


@pytest.mark.parametrize("value", ["feature", "change", "bug"])
def test_canonical_tokens_pass_through(value):
    assert normalize_intent(value) == value


@pytest.mark.parametrize(
    "value,expected",
    [("feat", "feature"), ("fix", "bug"), ("bugfix", "bug"), ("fixup", "bug")],
)
def test_canonical_aliases(value, expected):
    assert normalize_intent(value) == expected


@pytest.mark.parametrize("value", ["docs", "test", "chore", "merge", "refactor"])
def test_other_single_tokens_are_kept(value):
    """Adopted repos seed intent from git conventional-commit types; keep them."""
    assert normalize_intent(value) == value


def test_case_and_whitespace_are_normalized():
    assert normalize_intent("  Feature ") == "feature"
    assert normalize_intent("FIX") == "bug"


@pytest.mark.parametrize(
    "value",
    [
        "Clear 5 compliance triage bloat items (G2 stoplist + G3 ADR stubs)",
        "Re-aggregate triage inbox to surface SBOM bug cluster",
        "Verify CLAUDE.md is already <= 300 LOC and not in bloat baseline",
    ],
)
def test_free_text_description_collapses_to_default(value):
    """The core bug: a leaked description must not land in the Type column."""
    assert normalize_intent(value) == "change"


def test_empty_and_none_collapse_to_default():
    assert normalize_intent("") == "change"
    assert normalize_intent(None) == "change"


def test_custom_default():
    assert normalize_intent("", default="section") == "section"
    assert normalize_intent("a long leaked sentence here", default="x") == "x"


def test_overlong_single_token_collapses():
    """A hyphen-joined slug with no spaces but over the token cap is not a type."""
    assert normalize_intent("re-aggregate-triage-inbox-and-refresh") == "change"
