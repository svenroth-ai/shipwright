"""The derived catalogue's serialized form (FR-01.13, trg-1aa5a8ab).

Split from ``test_derived_catalogue.py`` at the 300-LOC cap. Covers
``.shipwright/adopt/derived-catalogue.json`` — the machine-readable copy that
lets traceability, coverage and drift consumers tell an unconfirmed catalogue
from a confirmed one without parsing prose.

**Reading it fails closed, and that asymmetry is the point.** The reconstructed
catalogue decides whether the confirmation follow-up gets filed, so a lenient
read is the one outcome that silently defeats the guarantee: ``bool("false")``
is ``True``, and a hand-edited document could otherwise report zero unconfirmed
requirements and silence the card.

@FR-01.13
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.derived_catalogue import (  # noqa: E402
    CONFIRMATION_DEDUP_KEY,
    SUMMARY_REL,
    confirmation_triage,
    summarize,
)
from lib.derived_catalogue_doc import (  # noqa: E402
    CatalogueDocumentError,
    catalogue_from_document,
    to_document,
    write_summary,
)

FEATURES = [
    {"fr_id": "FR-01.01", "label": "Sign in", "source_file": "src/auth.ts"},
    {"fr_id": "FR-01.02", "label": "Dashboard", "url": "http://localhost:5173/"},
    {"fr_id": "FR-01.03", "label": "Something nobody evidenced"},
]


# --------------------------------------------------------------------------- #
# The document + its file
# --------------------------------------------------------------------------- #

def test_document_is_schema_versioned_and_carries_every_row() -> None:
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    assert doc["schema_version"] == 1
    assert doc["generated_by"] == "shipwright-adopt"
    assert doc["split_name"] == "01-adopted"
    assert doc["total"] == 3
    assert doc["unconfirmed"] == 3
    assert doc["confirmed"] == 0
    assert doc["by_basis"] == {"assumed": 1, "code": 1, "observed": 1}
    assert doc["requirements"][0] == {
        "fr_id": "FR-01.01", "name": "Sign in", "basis": "code", "confirmed": False,
    }


def test_write_summary_round_trips_through_disk(tmp_path: Path) -> None:
    cat = summarize(FEATURES, split_name="01-adopted")
    path = write_summary(tmp_path, cat)
    assert path == tmp_path / SUMMARY_REL
    assert json.loads(path.read_text(encoding="utf-8")) == to_document(cat)


def test_write_summary_is_idempotent(tmp_path: Path) -> None:
    cat = summarize(FEATURES, split_name="01-adopted")
    first = write_summary(tmp_path, cat).read_text(encoding="utf-8")
    assert write_summary(tmp_path, cat).read_text(encoding="utf-8") == first


# --------------------------------------------------------------------------- #
# The follow-up card
# --------------------------------------------------------------------------- #

def test_confirmation_card_names_the_count_and_the_method() -> None:
    card = confirmation_triage(summarize(FEATURES, split_name="01-adopted"),
                               split_name="01-adopted")
    assert card is not None
    assert "3" in card["title"]
    assert "requirement-elicitation.md" in card["detail"]
    assert ".shipwright/planning/01-adopted/spec.md" in card["detail"]
    assert card["kind"] == "improvement"
    assert card["severity"] == "high"


def test_confirmation_card_dedup_key_does_not_vary_with_the_count() -> None:
    """External review O5. A key that carried the count would file a SECOND card
    on the next adopt run that detects one more route."""
    a = confirmation_triage(summarize(FEATURES, split_name="01-adopted"),
                            split_name="01-adopted")
    b = confirmation_triage(summarize(FEATURES[:1], split_name="01-adopted"),
                            split_name="01-adopted")
    assert a["dedup_key"] == b["dedup_key"] == CONFIRMATION_DEDUP_KEY


def test_no_card_when_every_requirement_was_confirmed_by_a_person() -> None:
    cat = summarize([{"fr_id": "FR-01.01", "label": "x", "basis": "interview"}],
                    split_name="01-adopted")
    assert confirmation_triage(cat, split_name="01-adopted") is None


# --------------------------------------------------------------------------- #
# Reading a catalogue back fails closed (external code review, high)
# --------------------------------------------------------------------------- #

def test_a_written_catalogue_reads_back_identically() -> None:
    cat = summarize(FEATURES, split_name="01-adopted")
    back = catalogue_from_document(to_document(cat))
    assert back == cat


def test_a_truthy_string_is_not_confirmation() -> None:
    """The finding this guard exists for. `bool("false")` is True, so a lenient
    read of a hand-edited catalogue would report zero unconfirmed requirements
    and silence the follow-up — defeating the one guarantee the file carries."""
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc["requirements"][0]["confirmed"] = "false"
    with pytest.raises(CatalogueDocumentError, match="real boolean"):
        catalogue_from_document(doc)


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("schema_version"),
    lambda d: d.update(schema_version=2),
    lambda d: d.update(requirements=[]),
    lambda d: d.update(requirements="nope"),
    lambda d: d.update(requirements=["FR-01.01"]),
    lambda d: d["requirements"][0].update(fr_id=""),
    lambda d: d["requirements"][0].pop("confirmed"),
])
def test_a_malformed_catalogue_is_rejected(mutate) -> None:
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    mutate(doc)
    with pytest.raises(CatalogueDocumentError):
        catalogue_from_document(doc)


def test_a_document_that_contradicts_its_own_entries_is_rejected() -> None:
    """Counts are recomputed from the entries, which are the ground truth — but
    a stated total that disagrees is REJECTED rather than quietly overridden,
    because the disagreement is itself the signal that the file was tampered
    with or half-written."""
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc["unconfirmed"] = 0
    with pytest.raises(CatalogueDocumentError, match="contradicts itself"):
        catalogue_from_document(doc)


def test_the_card_states_its_count_as_of_onboarding() -> None:
    """The triage layer has no update path, so a card claiming to hold the
    CURRENT number would go stale on a re-adopt. An as-of statement stays true,
    and the live figure lives in the artifact the card points at."""
    card = confirmation_triage(summarize(FEATURES, split_name="01-adopted"),
                               split_name="01-adopted")
    assert "at onboarding" in card["title"]
    assert "as of\nonboarding" in card["detail"] or "as of onboarding" in card["detail"]
    assert SUMMARY_REL in card["detail"]


def test_confirmation_cannot_be_claimed_without_an_interview_basis() -> None:
    """External code review, round 3 — the same hole as the truthy string, one
    level deeper. Requiring a real boolean is not enough on its own: a
    count-consistent document could set every row to `basis: code, confirmed:
    true` and pass, suppressing the follow-up. Confirmation is not an independent
    fact; it IS `basis in CONFIRMED_BASES`."""
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc["requirements"][0]["confirmed"] = True
    doc["confirmed"], doc["unconfirmed"] = 1, 2   # counts kept self-consistent
    with pytest.raises(CatalogueDocumentError, match="contradicts `basis`"):
        catalogue_from_document(doc)


def test_an_interview_row_claiming_to_be_unconfirmed_is_also_rejected() -> None:
    """The rule bites in both directions — a lie about provenance is a lie
    whichever way it leans, and only a symmetric check makes the field derivable
    rather than assertable."""
    doc = to_document(summarize(
        [{"fr_id": "FR-01.01", "label": "x", "basis": "interview"}],
        split_name="01-adopted"))
    doc["requirements"][0]["confirmed"] = False
    doc["confirmed"], doc["unconfirmed"] = 0, 1
    with pytest.raises(CatalogueDocumentError, match="contradicts `basis`"):
        catalogue_from_document(doc)


def test_a_row_without_a_basis_is_rejected() -> None:
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc["requirements"][0]["basis"] = "  "
    with pytest.raises(CatalogueDocumentError, match="non-empty string"):
        catalogue_from_document(doc)


def test_an_interview_backed_document_round_trips() -> None:
    """The rule must not block the state it exists to make reachable."""
    cat = summarize([{"fr_id": "FR-01.01", "label": "x", "basis": "interview"}],
                    split_name="01-adopted")
    back = catalogue_from_document(to_document(cat))
    assert back == cat
    assert back.confirmed == 1
