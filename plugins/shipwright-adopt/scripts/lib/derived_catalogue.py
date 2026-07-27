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
``lib.render_helpers``, and a later step will import this module in an
interpreter that must leave ``lib`` free for the shared ``triage``'s own
``lib.file_lock``.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
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


#: Sentinel under which ``spec_table`` is memoized when loaded BY PATH.
_SPEC_TABLE_SENTINEL = "_shipwright_adopt_spec_table"


def _row_helpers():
    """``spec_table.basis_for`` / ``effective_features``, resolved late and BY PATH.

    Deliberately not ``from lib.spec_table import …``. Which package the name
    ``lib`` resolves to is a property of the *process*, not of this file, and
    another plugin's test session can rebind it after adopt's modules loaded —
    ``shipwright-compliance``'s Group-I round-trip test imports adopt's
    ``_render_spec_md`` and runs after tests that bind ``lib`` to compliance's
    own package, at which point ``lib.spec_table`` stops existing. That is the
    ADR-045 collision, and a name-based import cannot be made immune to it.

    A path-based load under a sentinel is (`validate_adoption._discovery`,
    `baseline_generator`, `spec_table._load_shared` all use it). ``scripts`` is
    put on ``sys.path`` first so ``spec_table``'s own ``lib.render_helpers``
    import resolves against ADOPT's tree; the module is registered BEFORE
    ``exec_module`` for the dataclass reason documented in ``_load_shared``.
    """
    module = sys.modules.get(_SPEC_TABLE_SENTINEL)
    if module is None:
        lib_dir = Path(__file__).resolve().parent
        scripts_dir = lib_dir.parent
        # BOTH, because `spec_table` reaches `render_helpers` two ways: the
        # normal `lib.render_helpers` (needs `scripts`) and the bare fallback it
        # takes when `lib` belongs to another plugin (needs `lib`). Under a
        # foreign `lib` only the second can work, so only adding `scripts` would
        # move the failure one import down instead of fixing it.
        for entry in (str(scripts_dir), str(lib_dir)):
            if entry not in sys.path:
                sys.path.insert(0, entry)
        spec = importlib.util.spec_from_file_location(
            _SPEC_TABLE_SENTINEL, lib_dir / "spec_table.py")
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise ImportError("could not load adopt's spec_table by path")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_SPEC_TABLE_SENTINEL] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(_SPEC_TABLE_SENTINEL, None)
            raise
    return module.basis_for, module.effective_features


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

    **It states what is true of THIS catalogue, not a fixed sentence.** A block
    whose whole job is honesty must not say "nobody has confirmed them" once some
    rows are ``Basis: interview`` — which is reachable the moment the elicitation
    follow-up starts landing answers. Three cases, and only the first says
    "nobody" (external code review).
    """
    n, confirmed, unconfirmed = (
        catalogue.total, catalogue.confirmed, catalogue.unconfirmed,
    )
    tally = ", ".join(f"{count} {basis}" for basis, count in catalogue.by_basis.items())

    if unconfirmed == 0:
        all_confirmed = (
            f"> All **{n}** were worked through with someone who knows the product "
            f"(`Basis: interview`), so measurements against them describe the "
            "product rather than a catalogue nobody checked."
        )
        return "\n".join([
            "> **These requirements have been confirmed with a person.**",
            ">",
            all_confirmed,
            ">",
            f"> - How each row was established is its `Basis` cell ({tally}).",
            f"> - Machine-readable copy: `{SUMMARY_REL}`.",
        ])

    if confirmed:
        headline = (
            f"> **{unconfirmed} of these {n} requirements were derived by reading "
            "the code and are still unconfirmed.**"
        )
        body = (
            f"> **{confirmed}** have been worked through with a person; the other "
            f"**{unconfirmed}** were read out of this codebase and nobody has "
            "agreed they describe what the software is actually for."
        )
    else:
        headline = (
            "> **These requirements were derived by reading the code — nobody has "
            "confirmed them yet.**"
        )
        body = (
            f"> `/shipwright-adopt` derived **{n}** requirement(s) from this "
            f"codebase, of which **{unconfirmed} are unconfirmed**: no person has "
            "agreed that they describe what this software is actually for. "
            "Reading the code is a start; it is not enough on its own."
        )

    # Each multi-fragment line is joined OUTSIDE the list literal. Adjacent
    # string literals inside a list are implicitly concatenated, so a missing
    # comma silently merges two entries into one instead of failing — CodeQL
    # `py/implicit-string-concatenation-in-list` flags exactly that shape, and in
    # a block whose whole job is to state counts precisely it is worth avoiding.
    caveat = (
        "> Until they are confirmed, anything measured against them — "
        "traceability, coverage, drift — describes *this catalogue*, not the "
        "product. Treat the numbers accordingly."
    )
    next_step = (
        "> - **Next step:** work through the unconfirmed ones with someone who "
        f"knows the product, following `{ELICITATION_DOC}`. Onboarding filed the "
        f"follow-up in the Triage Inbox as `{CONFIRMATION_DEDUP_KEY}`."
    )
    return "\n".join([
        headline,
        ">",
        body,
        ">",
        caveat,
        ">",
        f"> - How each row was derived is its `Basis` cell ({tally}).",
        f"> - Machine-readable copy: `{SUMMARY_REL}`.",
        next_step,
    ])


__all__ = [
    "CONFIRMATION_DEDUP_KEY",
    "CONFIRMED_BASES",
    "ELICITATION_DOC",
    "SUMMARY_REL",
    "DerivedCatalogue",
    "DerivedRequirement",
    "render_provenance_banner",
    "summarize",
]
