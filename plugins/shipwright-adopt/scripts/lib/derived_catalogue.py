"""A derived requirements catalogue that says so (FR-01.13, trg-1aa5a8ab).

Onboarding writes a requirements catalogue by reading code. Until this module,
nothing in the handed-over repository said that — so traceability, coverage and
drift all measured against a catalogue that *looked* confirmed and was not. This
repository is the proof: its own catalogue came from onboarding, and a whole
campaign now exists to repair it years later.

**Where the marking lives, and why not in the table.** Two obvious places are
closed, on evidence rather than taste:

* not a new column — ``fr_table_shape.FR_TABLE_COLUMNS`` is an explicit
  two-sided contract shared with the greenfield producer and the compliance
  reader, so adding one is a three-plugin change;
* not a qualifier on ``Basis`` — ``fr_basis.classify`` scores a vocabulary value
  carrying a qualifier as **malformed and blocking** (audit check ``I5``), so
  ``code (unconfirmed)`` would fail the audit it is meant to inform.

Both are also the wrong altitude. "Nobody has confirmed this catalogue" is a
claim about the *catalogue*, not about any one row — so it is stated once, above
the table, in prose a human reads, and once more in JSON a machine reads.

**Derived ≠ unconfirmed.** ``Basis`` already answers *how we know* (`code`,
`observed`, `assumed`). What it does not answer is whether a person ever agreed.
Exactly one vocabulary value carries that (``interview``), so ``confirmed`` is
derived from it — nothing adopt emits today qualifies, and a later elicitation
pass changes the count without touching this module.

Rows come from ``spec_table.effective_features``, the same list the table is
rendered from, so the reported count cannot describe a different catalogue than
the one handed over.

The serialized side — ``to_document`` / ``catalogue_from_document`` /
``write_summary`` — lives in the sibling ``derived_catalogue_doc`` (300-LOC cap),
which imports this module and never the other way round.

Pure. **Binds no ``lib`` package at import time** (ADR-045): ``spec_table`` is
reached lazily from ``summarize`` alone, because it transitively imports
``lib.render_helpers``, and Step E.18 imports this module in an interpreter that
must leave ``lib`` free for the shared ``triage``'s own ``lib.file_lock``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Where the machine-readable copy lands, relative to the adopted repo root.
#: Written by ``derived_catalogue_doc.write_summary``; named here because both
#: the banner and the follow-up card point a reader at it.
SUMMARY_REL = ".shipwright/adopt/derived-catalogue.json"

#: Stable across runs and independent of the count, so a re-adopt that detects
#: one more route updates nothing and duplicates nothing. The count lives in the
#: card's text and, authoritatively, in ``SUMMARY_REL``.
CONFIRMATION_DEDUP_KEY = "adopt-derived-catalogue-confirmation"

#: The shared grilling method the follow-up asks for. Binding for every plugin
#: that elicits a requirement from a human.
ELICITATION_DOC = "shared/requirement-elicitation.md"

#: The only ``Basis`` value that means a person said so. Everything else —
#: including ``tests``, which is still a machine reading an artefact — leaves the
#: requirement unconfirmed.
CONFIRMED_BASES = frozenset({"interview"})


@dataclass(frozen=True)
class DerivedRequirement:
    fr_id: str
    name: str
    basis: str
    confirmed: bool


@dataclass(frozen=True)
class DerivedCatalogue:
    split_name: str
    requirements: tuple[DerivedRequirement, ...]

    @property
    def total(self) -> int:
        return len(self.requirements)

    @property
    def confirmed(self) -> int:
        return sum(1 for r in self.requirements if r.confirmed)

    @property
    def unconfirmed(self) -> int:
        return self.total - self.confirmed

    @property
    def by_basis(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for r in self.requirements:
            tally[r.basis] = tally.get(r.basis, 0) + 1
        return dict(sorted(tally.items()))


def _row_helpers():
    """``spec_table.basis_for`` / ``effective_features``, imported late.

    Dual-mode for the two ways adopt's modules are loaded — bare when a tool put
    ``scripts/lib`` on the path, package-qualified when ``scripts`` is there
    (tests, ``artifact_writer``). Same shape as ``baseline_generator``'s
    ``shared_loader`` import, and for the same reason.
    """
    try:  # tool context: lib/ is on sys.path
        from spec_table import basis_for, effective_features  # noqa: PLC0415
    except ImportError:  # test / package context: scripts/ on sys.path
        from lib.spec_table import basis_for, effective_features  # noqa: PLC0415
    return basis_for, effective_features


def summarize(features: list[dict[str, Any]], *, split_name: str) -> DerivedCatalogue:
    """Describe the catalogue ``render_fr_table`` is about to render."""
    basis_for, effective_features = _row_helpers()
    return DerivedCatalogue(
        split_name=split_name,
        requirements=tuple(
            DerivedRequirement(
                fr_id=f.get("fr_id", "FR-01.?"),
                name=f.get("label", f.get("route", "?")),
                basis=(basis := basis_for(f)),
                confirmed=basis in CONFIRMED_BASES,
            )
            for f in effective_features(features)
        ),
    )


def render_provenance_banner(catalogue: DerivedCatalogue) -> str:
    """The block that goes above the FR table, in plain words.

    **Prose only, and interpolating nothing but counts.** Every FR-table consumer
    in the framework is line-based on a leading ``|``; a banner line starting with
    one would be read as a requirement row, or worse as a header that invalidates
    the column map for every row beneath it. Keeping detected text out entirely is
    why a pipe in a repo's code comments cannot reach this block — stronger than
    escaping it afterwards, because there is nothing to escape.
    """
    n, unconfirmed = catalogue.total, catalogue.unconfirmed
    tally = ", ".join(f"{count} {basis}" for basis, count in catalogue.by_basis.items())
    lines = [
        "> **These requirements were derived by reading the code — nobody has "
        "confirmed them yet.**",
        ">",
        f"> `/shipwright-adopt` derived **{n}** requirement(s) from this codebase, "
        f"of which **{unconfirmed} are unconfirmed**: no person has agreed that "
        "they describe what this software is actually for. Reading the code is a "
        "start; it is not enough on its own.",
        ">",
        "> Until they are confirmed, anything measured against them — "
        "traceability, coverage, drift — describes *this catalogue*, not the "
        "product. Treat the numbers accordingly.",
        ">",
        f"> - How each row was derived is its `Basis` cell ({tally}).",
        f"> - Machine-readable copy: `{SUMMARY_REL}`.",
        f"> - **Next step:** work through them with someone who knows the product, "
        f"following `{ELICITATION_DOC}`. Onboarding filed the follow-up in the "
        f"Triage Inbox as `{CONFIRMATION_DEDUP_KEY}`.",
    ]
    return "\n".join(lines)


def confirmation_triage(
    catalogue: DerivedCatalogue, *, split_name: str,
) -> dict[str, Any] | None:
    """The follow-up that takes the derived catalogue to a person.

    Returns ``None`` when every requirement was already confirmed — there is
    nothing to ask. Filed by Step E.18, which is the first step that runs after
    the Triage Inbox exists (Step E.16).

    The count is stated **as of onboarding**, not as a live figure. The dedup key
    is deliberately count-free so a re-adopt duplicates nothing, and the triage
    layer has no update path — so a card claiming to hold the current number
    would go quietly stale (external code review). An as-of statement stays true,
    and the card points at ``SUMMARY_REL`` for what is true now.
    """
    if catalogue.unconfirmed == 0:
        return None
    spec_rel = f".shipwright/planning/{split_name}/spec.md"
    return {
        "dedup_key": CONFIRMATION_DEDUP_KEY,
        "severity": "high",
        "kind": "improvement",
        "title": (
            f"Confirm the derived requirements catalogue with a person "
            f"({catalogue.unconfirmed} unconfirmed at onboarding)"
        ),
        "detail": (
            f"At onboarding, {catalogue.total} requirement(s) in `{spec_rel}` were "
            f"derived by reading this codebase and {catalogue.unconfirmed} had been "
            f"confirmed by nobody. Work through them with someone who knows the "
            f"product, following `{ELICITATION_DOC}` — one question at a time, each "
            f"with a recommendation, and not finished until every context dimension "
            f"is answered or explicitly recorded as an assumption. Update each row's "
            f"`Basis` to `interview` as it is confirmed. These figures are as of "
            f"onboarding; `{SUMMARY_REL}` carries the current ones and is refreshed "
            f"on every adopt run."
        ),
        "fr_id": None,
    }


__all__ = [
    "CONFIRMATION_DEDUP_KEY",
    "CONFIRMED_BASES",
    "ELICITATION_DOC",
    "SUMMARY_REL",
    "DerivedCatalogue",
    "DerivedRequirement",
    "confirmation_triage",
    "render_provenance_banner",
    "summarize",
]
