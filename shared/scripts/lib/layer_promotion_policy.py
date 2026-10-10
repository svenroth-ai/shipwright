"""Which specs the automated ``Layers`` promotion must never touch.

The adopted spec (``<planning>/01-adopted/spec.md``) is the framework's LIVE
requirements catalog and stays advisory by decision (campaign "Requirements
Catalog", SPEC §6.2, ADR-108): every ``Layers`` cell keeps the literal
``(inferred)`` marker, because an unmarked cell flips the requirement's
provenance to ``explicit`` and a coverage gap then hard-aborts the
layer-coverage gate (``sys.exit(1)``, unbypassable). Four integration guards
pin that (``test_fr_table_shape_convergence.py`` x3,
``test_requirements_catalog_contract.py`` x1).

P3.5 promotion deliberately writes explicit cells, so it must stay out of an
advisory spec — otherwise every iterate re-opens a promotion PR the guards
reject. The rule keys on the split name, so a brownfield project's own
``01-adopted`` spec (seeded ``(inferred)`` by /shipwright-adopt) stays advisory
too. Advisory FRs can still ESCALATE (ledger contradictions stay visible); they
are never promoted.
"""

from __future__ import annotations

#: Split directory names whose spec stays advisory (never promoted).
ADVISORY_SPLIT_DIRS = frozenset({"01-adopted"})

#: Named skip reason, so a caller need not string-compare prose.
SKIP_ADVISORY_SPEC = "advisory_spec_never_promoted"


def is_advisory_spec(spec_path: str | None) -> bool:
    """Whether ``spec_path`` (a repo-relative ``.../<split>/spec.md``) lives in
    a split directory that must keep ``(inferred)`` Layers cells."""
    parts = (spec_path or "").replace("\\", "/").split("/")
    return len(parts) >= 2 and parts[-2] in ADVISORY_SPLIT_DIRS
