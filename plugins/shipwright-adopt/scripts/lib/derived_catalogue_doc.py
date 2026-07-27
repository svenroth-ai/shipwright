"""The serialized side of the derived catalogue (FR-01.13, trg-1aa5a8ab).

``.shipwright/adopt/derived-catalogue.json`` — how many requirements onboarding
derived and how many nobody has confirmed, in a form traceability, coverage and
drift consumers can read without parsing prose.

Split from ``derived_catalogue`` at the 300-LOC source cap. One-way dependency:
this module imports the model, never the reverse. Imports no ``lib`` package, so
a later step can load it bare without binding one (ADR-045).

**Reading fails closed, and that asymmetry is deliberate.** The reconstructed
catalogue decides whether the confirmation follow-up gets filed at all, so every
failure mode here must be "stop", never "nothing to ask" — a lenient read is the
one outcome that silently defeats the guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:  # tool context: lib/ is on sys.path
    from derived_catalogue import (
        CONFIRMED_BASES,
        SUMMARY_REL,
        DerivedCatalogue,
        DerivedRequirement,
    )
except ImportError:  # test / package context: scripts/ on sys.path
    from lib.derived_catalogue import (  # type: ignore[no-redef]
        CONFIRMED_BASES,
        SUMMARY_REL,
        DerivedCatalogue,
        DerivedRequirement,
    )


class CatalogueDocumentError(ValueError):
    """A catalogue document that cannot be trusted to say what was confirmed."""


def to_document(catalogue: DerivedCatalogue) -> dict[str, Any]:
    """The JSON shape written to :data:`SUMMARY_REL`."""
    return {
        "schema_version": 1,
        "generated_by": "shipwright-adopt",
        "split_name": catalogue.split_name,
        "total": catalogue.total,
        "confirmed": catalogue.confirmed,
        "unconfirmed": catalogue.unconfirmed,
        "by_basis": catalogue.by_basis,
        "requirements": [
            {"fr_id": r.fr_id, "name": r.name, "basis": r.basis,
             "confirmed": r.confirmed}
            for r in catalogue.requirements
        ],
    }


def write_summary(project_root: Path, catalogue: DerivedCatalogue) -> Path:
    """Write the machine-readable copy. Idempotent — a re-adopt overwrites."""
    out = Path(project_root) / SUMMARY_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(to_document(catalogue), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out


def catalogue_from_document(doc: dict[str, Any]) -> DerivedCatalogue:
    """Rebuild a catalogue from :func:`to_document` output. **Fails closed.**

    How a later step reads what Step E wrote, without re-deriving anything from
    the features — one derivation, one answer.

    Two rules, both closing the same hole one level apart — a document that
    claims confirmation nobody gave, thereby suppressing the follow-up this whole
    mechanism exists to guarantee. Both were found by external code review, and
    the second only after the first was fixed:

    * ``confirmed`` must be a real boolean. A lenient read makes
      ``bool("false")`` true.
    * ``confirmed`` must **agree with** ``basis``. Requiring a boolean is not
      enough on its own: a count-consistent document could set every row to
      ``{"basis": "code", "confirmed": true}`` and pass. Confirmation is not an
      independent fact — it is exactly ``basis in CONFIRMED_BASES``, so a row
      asserting otherwise (in either direction) is rejected. No row can claim a
      person agreed without saying that person is the source.

    Counts are recomputed from the entries, which are the ground truth; a stated
    ``total`` / ``unconfirmed`` that disagrees with them is **rejected** rather
    than quietly overridden, because the disagreement is itself the signal.
    """
    if doc.get("schema_version") != 1:
        raise CatalogueDocumentError(
            f"unsupported schema_version {doc.get('schema_version')!r} (expected 1)")
    raw_rows = doc.get("requirements")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise CatalogueDocumentError("`requirements` must be a non-empty list")

    rows: list[DerivedRequirement] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise CatalogueDocumentError("each requirement must be an object")
        fr_id = raw.get("fr_id")
        if not isinstance(fr_id, str) or not fr_id.strip():
            raise CatalogueDocumentError("each requirement needs a non-empty `fr_id`")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CatalogueDocumentError(f"{fr_id}: `name` must be a non-empty string")
        confirmed = raw.get("confirmed")
        if not isinstance(confirmed, bool):
            raise CatalogueDocumentError(
                f"{fr_id}: `confirmed` must be a real boolean, got {confirmed!r} — "
                "a truthy string here would mark an unconfirmed requirement as "
                "confirmed and silence the follow-up"
            )
        basis = raw.get("basis")
        if not isinstance(basis, str) or not basis.strip():
            raise CatalogueDocumentError(f"{fr_id}: `basis` must be a non-empty string")
        basis = basis.strip()
        if confirmed != (basis in CONFIRMED_BASES):
            raise CatalogueDocumentError(
                f"{fr_id}: `confirmed`={confirmed} contradicts `basis`={basis!r} — "
                f"confirmation is not an independent fact, it is exactly "
                f"`basis in {sorted(CONFIRMED_BASES)}`. A row cannot claim a person "
                f"agreed without naming that person as the source."
            )
        rows.append(DerivedRequirement(
            fr_id=fr_id, name=name, basis=basis, confirmed=confirmed,
        ))

    catalogue = DerivedCatalogue(
        split_name=str(doc.get("split_name") or ""), requirements=tuple(rows),
    )
    # REQUIRED, not "checked if present": an optional cross-check is dodged by
    # deleting the field, which is the cheapest possible forgery.
    for key, actual in (("total", catalogue.total),
                        ("confirmed", catalogue.confirmed),
                        ("unconfirmed", catalogue.unconfirmed),
                        ("by_basis", catalogue.by_basis)):
        if key not in doc:
            raise CatalogueDocumentError(f"`{key}` is required")
        if doc[key] != actual:
            raise CatalogueDocumentError(
                f"`{key}` says {doc[key]!r} but the entries say {actual!r} — "
                "the document contradicts itself, so neither is trusted"
            )
    return catalogue


def read_summary(project_root: Path) -> DerivedCatalogue:
    """Load :data:`SUMMARY_REL` from disk **through the fail-closed reader**.

    The one sanctioned way for a consumer to read the catalogue. Reaching for
    ``json.loads`` and pulling ``doc["unconfirmed"]`` out directly would skip
    every check in :func:`catalogue_from_document` — and it would skip them at
    the handover, which is the single place the count is published. A forged or
    half-written document must not be able to put a false number in the adoption
    commit (external code review, high).
    """
    path = Path(project_root) / SUMMARY_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogueDocumentError(f"{SUMMARY_REL} is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogueDocumentError(f"{SUMMARY_REL} is unreadable: {exc}") from exc
    if not isinstance(doc, dict):
        raise CatalogueDocumentError(f"{SUMMARY_REL} is not a JSON object")
    return catalogue_from_document(doc)


__all__ = [
    "CatalogueDocumentError",
    "catalogue_from_document",
    "read_summary",
    "to_document",
    "write_summary",
]
