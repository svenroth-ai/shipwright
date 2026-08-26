"""Reading FR rows off disk for Group I — the row scanner (campaign S4).

Extracted verbatim from ``group_i`` when I6 arrived and the findings module hit
its size limit. Pure move, no behaviour change; ``group_i`` re-exports every
name here, so ``group_i.FrRow`` / ``.scan_specs`` / ``.scan_fr_rows`` remain the
single entry point callers and tests already use — the same pattern the module
already follows for ``group_i_detectors`` and ``group_i_scan``.

The dependency runs ONE way: this module never imports ``group_i``. Group I is
the sole importer of its siblings, which keeps the findings layer on top of the
reading layer rather than tangled with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.audit.audit_adapters import load_shared_lib
from scripts.audit.group_i_scan import SpecScan


@dataclass(frozen=True)
class FrRow:
    """One FR row. ``name`` is empty when the table has no Name column.

    ``retired`` marks a row under ``### Removed Requirements``. Retired rows are
    never linted (they are history), but they DO participate in the I4 duplicate
    check: `fr-authoring.md` §4 requires a retired number never be reused.
    """

    id: str
    name: str
    description: str
    split: str
    spec_path: str
    retired: bool = False
    #: Raw ``Basis`` cell (campaign S5), and whether a column literally headed
    #: ``Basis`` supplied it. A spec predating the column has neither, and I5
    #: skips it rather than scoring a legacy ``Source`` path as a typo.
    basis: str = ""
    basis_declared: bool = False


def _scan_one_spec(
    path: Path, split: str, spec_path: str, rejects: list | None = None,
) -> list[FrRow]:
    """Project ``fr_table_reader`` rows onto the Name/Description pair I1–I3 lint.

    Hygiene is the one consumer that needs the Name and Description cells kept
    APART (the §5 name fence applies to names only), which is why ``FrRow``
    survives while the scan behind it does not. The scan it replaces carried two
    defects the shared reader does not: it required the id column to be headed
    literally ``ID``, so the whole traceability-fixture shape audited as zero
    rows (FV-4), and it reset its column mapping at EVERY heading, silently
    dropping every FR row under a later heading (FV-5).
    """
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    return [
        FrRow(
            id=row.id,
            name=row.name,
            description=row.text,
            split=split,
            spec_path=spec_path,
            retired=row.removed,
            basis=row.basis_cell,
            basis_declared=row.basis_from_named_col,
        )
        for row in load_shared_lib("fr_table_reader").read_fr_rows(
            content, rejects=rejects,
        )
    ]


def scan_specs(project_root: Path, *, include_retired: bool = False) -> SpecScan:
    """Rows under ``.shipwright/planning/<split>/spec.md``, plus why there are none.

    Live rows only by default — that is what the prose checks lint. Pass
    ``include_retired=True`` for the I4 number-reuse check, which must see
    ``### Removed Requirements`` rows too.

    The declined rows ride along in ``SpecScan.rejects`` so an empty result can
    say WHICH of the six no-rows states it is (see ``group_i_scan``). They come
    from the shared reader's own accumulator — the same data published on the
    traceability manifest as ``invalid_ids`` — rather than being re-derived here.
    """
    planning = project_root / ".shipwright" / "planning"
    rows: list[FrRow] = []
    rejects: list = []
    any_spec = False
    # require="is_file" is this call site's divergence from the majority's
    # "exists": a *directory* named spec.md is not scanned. Sorting before vs
    # after the is_dir filter is equivalent (one shared parent), so the shared
    # helper's sort-first order matches the previous filter-first one.
    iter_spec_files = load_shared_lib("planning_discovery").iter_spec_files
    for spec in iter_spec_files(
        planning, guard="is_dir", sort=True, include_iterate=True, require="is_file"
    ):
        any_spec = True
        split_name = spec.parent.name
        rel = f".shipwright/planning/{split_name}/spec.md"
        rows.extend(_scan_one_spec(spec, split_name, rel, rejects))
    retired_count = sum(1 for r in rows if r.retired)
    if not include_retired:
        rows = [r for r in rows if not r.retired]
    return SpecScan(rows=rows, rejects=rejects, any_spec=any_spec,
                    retired_count=retired_count)


def scan_fr_rows(project_root: Path, *, include_retired: bool = False) -> list[FrRow]:
    """``scan_specs`` projected to just the rows (the pre-S5 signature)."""
    return scan_specs(project_root, include_retired=include_retired).rows


__all__ = ["FrRow", "scan_fr_rows", "scan_specs"]
