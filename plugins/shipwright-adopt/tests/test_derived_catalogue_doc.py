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

from lib.derived_catalogue import SUMMARY_REL, summarize  # noqa: E402
from lib.derived_catalogue_doc import (  # noqa: E402
    CatalogueDocumentError,
    catalogue_from_document,
    read_summary,
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


# --------------------------------------------------------------------------- #
# read_summary — the one sanctioned way a consumer reads the catalogue
# --------------------------------------------------------------------------- #

def test_read_summary_round_trips_what_write_summary_wrote(tmp_path: Path) -> None:
    cat = summarize(FEATURES, split_name="01-adopted")
    write_summary(tmp_path, cat)
    assert read_summary(tmp_path) == cat


def test_read_summary_applies_the_fail_closed_checks(tmp_path: Path) -> None:
    """The point of the helper: a consumer must not be able to reach the numbers
    without the integrity checks. A bare `json.loads` at the handover would skip
    them at the one place the count is published."""
    cat = summarize(FEATURES, split_name="01-adopted")
    write_summary(tmp_path, cat)
    doc = json.loads((tmp_path / SUMMARY_REL).read_text(encoding="utf-8"))
    doc["requirements"][0]["confirmed"] = True
    doc["confirmed"], doc["unconfirmed"] = 1, 2
    (tmp_path / SUMMARY_REL).write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(CatalogueDocumentError, match="contradicts `basis`"):
        read_summary(tmp_path)


@pytest.mark.parametrize("write", [
    lambda p: None,
    lambda p: p.write_text("{not json", encoding="utf-8"),
    lambda p: p.write_text("[]", encoding="utf-8"),
])
def test_read_summary_fails_closed_on_missing_or_unreadable(tmp_path, write) -> None:
    path = tmp_path / SUMMARY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    write(path)
    with pytest.raises(CatalogueDocumentError):
        read_summary(tmp_path)


@pytest.mark.parametrize("key", ["total", "confirmed", "unconfirmed", "by_basis"])
def test_a_document_missing_a_declared_total_is_rejected(key: str) -> None:
    """Required, not "checked if present" — an optional cross-check is dodged by
    deleting the field, the cheapest possible forgery."""
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc.pop(key)
    with pytest.raises(CatalogueDocumentError, match="required"):
        catalogue_from_document(doc)


def test_a_wrong_by_basis_tally_is_rejected() -> None:
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc["by_basis"] = {"code": 99}
    with pytest.raises(CatalogueDocumentError, match="by_basis"):
        catalogue_from_document(doc)


def test_a_row_without_a_name_is_rejected() -> None:
    doc = to_document(summarize(FEATURES, split_name="01-adopted"))
    doc["requirements"][0]["name"] = "  "
    with pytest.raises(CatalogueDocumentError, match="`name`"):
        catalogue_from_document(doc)
