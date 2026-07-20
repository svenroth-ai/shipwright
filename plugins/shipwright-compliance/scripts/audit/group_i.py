"""Group I — Requirement Hygiene (detective-only).

Reports FR rows that drift from `shared/fr-authoring.md`: implementation detail
leaking into a requirement's name or description, change-deltas minted as their
own requirement, and duplicate FR IDs.

- I1 — FR name carries a verb / symbol / path / ADR number / iterate slug
- I2 — FR description carries implementation detail
- I3 — FR only describes a change to another FR (fold candidate)
- I4 — the same FR ID used twice anywhere in the catalog

**Advisory by construction, not by luck.** The three prose checks (I1/I2/I3)
never emit ``status="fail"``, because a failing finding feeds
``AuditReport.any_fail`` — which drives ``run_audit``'s exit code and the
compliance dashboard verdict. Legacy specs are expected to carry historical
violations, and the requirement is that they must not redden CI while a spec
cleans up gradually. The counts and IDs still ride in ``detail``, so no signal
is lost; only the verdict is left alone.

I4 is the exception and DOES fail: two rows claiming one FR ID is an objective
defect, not a style opinion. No finding is ever HIGH.

**Reads rows through the shared ``fr_table_reader``** (campaign S4). It used to
scan the table itself, on the argument that the authoritative readers collapse
the table to one semantic body field while hygiene needs Name and Description
kept apart. That argument held for the row SHAPE and is preserved — ``FrRow``
still separates them — but it did not justify a separate scan, and the separate
scan carried two defects of its own (FV-4, FV-5) that went unnoticed precisely
because nothing downstream consumes this group.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
    load_shared_lib,
)

# Detectors live in the pure sibling module; re-exported here so callers and
# tests keep a single entry point (`group_i.name_violations`, …).
from scripts.audit.group_i_detectors import (
    description_violations,
    is_fold_candidate,
    name_violations,
)
from scripts.audit.group_i_scan import STATE_ROWS, SpecScan, basis_tally


# ---------------------------------------------------------------------------
# Row scanner — one shared header-driven reader (campaign S4)
# ---------------------------------------------------------------------------


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
    for spec in iter_spec_files(planning, require="is_file"):
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


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

_PREVIEW_CAP = 5

_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("I1", "FR name carries implementation detail", "LOW"),
    ("I2", "FR description carries implementation detail", "LOW"),
    ("I3", "FR is a change-delta, not a capability", "LOW"),
    ("I4", "Duplicate FR ID in the catalog", "MEDIUM"),
    ("I5", "Malformed Basis value", "MEDIUM"),
)

#: I5's display name, bound by NAME rather than by `_CHECKS[4][1]`. The
#: positional form silently relabels the check if anyone reorders `_CHECKS`, and
#: every other check already passes its name literally.
_I5_NAME = next(name for cid, name, _sev in _CHECKS if cid == "I5")

#: I1/I2/I3 are prose heuristics over legacy specs, so they report WITHOUT
#: ``status="fail"``: a failing finding feeds ``AuditReport.any_fail``, which
#: flips ``run_audit``'s exit code and the dashboard verdict. The requirement is
#: explicit that existing violations must not redden CI — a spec should be able
#: to clean up gradually. The count and IDs still ride in ``detail``, so the
#: signal is fully preserved; only the verdict is left alone.
#:
#: I4 and I5 are excluded: a duplicate FR ID is an objective defect (two rows
#: claiming one identity) and a Basis value outside the closed vocabulary is a
#: typo, never legacy style noise, so both fail for real. `other` is NOT a
#: failure — see `_basis_finding`.
_ADVISORY_CHECKS = frozenset({"I1", "I2", "I3"})


def _finding(check_id: str, name: str, severity: str, status: str, detail: str) -> Finding:
    cmd = None
    if status == "fail":
        cmd = (
            f"/shipwright-iterate --type change "
            f"\"reword FRs flagged by {check_id} — see shared/fr-authoring.md\""
        )
    return Finding(
        group="I", check_id=check_id, name=name, severity=severity,
        source=SOURCE_DETECTIVE_ONLY, status=status, detail=detail,
        suggested_iterate_cmd=cmd,
    )


def _report(check_id: str, name: str, severity: str, hits: list[str], noun: str) -> Finding:
    if not hits:
        return _finding(check_id, name, severity, "pass", f"no {noun} found")
    preview = ", ".join(hits[:_PREVIEW_CAP])
    suffix = f" (+{len(hits) - _PREVIEW_CAP} more)" if len(hits) > _PREVIEW_CAP else ""
    advisory = check_id in _ADVISORY_CHECKS
    return _finding(
        check_id, name, severity,
        "pass" if advisory else "fail",
        f"{'advisory — ' if advisory else ''}{len(hits)} {noun}: {preview}{suffix}",
    )


def _basis_finding(rows: list[FrRow]) -> Finding:
    """I5 — score every declared ``Basis`` cell against the closed vocabulary.

    Severity is asymmetric by design (SPEC §3.2). A value outside the vocabulary
    FAILS: that is a typo, and a typo is not a special case. ``other`` is
    reported but never fails — it is the escape hatch for a genuine special case,
    and an escape hatch that blocks is not one. A row whose table has no ``Basis``
    column is skipped entirely rather than treated as empty-and-wrong, so
    adopting the column is not a breaking change for specs that predate it.
    """
    declared = [r for r in rows if r.basis_declared]
    if not declared:
        return _finding(
            "I5", _I5_NAME, "MEDIUM", "skip",
            "no Basis column in this spec shape — vocabulary not applicable",
        )

    noun = "malformed Basis value(s)"
    bad, other = basis_tally(declared, load_shared_lib("fr_basis").classify)
    if bad:
        return _report("I5", _I5_NAME, "MEDIUM", bad, noun)
    if other:
        return _finding(
            "I5", _I5_NAME, "MEDIUM", "pass",
            f"advisory — {len(other)} requirement(s) with Basis `other`: "
            + ", ".join(other[:_PREVIEW_CAP]),
        )
    return _report("I5", _I5_NAME, "MEDIUM", [], noun)


def run(
    project_root: Path,
    _config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run every I-group check. Absent specs SKIP rather than fail."""
    scan = scan_specs(project_root)
    rows = scan.rows
    if scan.state != STATE_ROWS:
        # Still a SKIP for every check — Group I is detective-only and a repo
        # without requirements must not redden CI. What S5 changed is that the
        # detail now names WHICH of the six no-rows states this is, instead of
        # one message that read the same for "no spec yet" and "a well-formed
        # table whose every id was declined".
        return [
            _finding(cid, name, sev, "skip", scan.detail)
            for cid, name, sev in _CHECKS
        ]

    described = [
        f"{r.id} ({'/'.join(description_violations(r.description))})"
        for r in rows if description_violations(r.description)
    ]
    folds = [r.id for r in rows if is_fold_candidate(r.description)]

    # I4 must see retired rows: §4 forbids reusing a removed FR's number. Dedup is
    # GLOBAL, not per-(split, id) — S6: one ID names one requirement across the whole
    # catalog. Stricter: a repo whose splits legally reuse IDs newly FAILs (see note).
    seen: dict[str, int] = {}
    for r in scan_fr_rows(project_root, include_retired=True):
        seen[r.id] = seen.get(r.id, 0) + 1
    dupes = sorted({fid for fid, n in seen.items() if n > 1})

    # The §5 name fence only applies to tables that HAVE a Name column.
    # Greenfield carries a single Requirement sentence instead, so reporting
    # "pass" there would be a false green over names never examined.
    if any(r.name for r in rows):
        named = [
            f"{r.id} ({'/'.join(name_violations(r.name))})"
            for r in rows if r.name and name_violations(r.name)
        ]
        i1 = _report("I1", _CHECKS[0][1], "LOW", named, "FR name(s) carrying implementation detail")
    else:
        i1 = _finding(
            "I1", _CHECKS[0][1], "LOW", "skip",
            "no Name column in this spec shape — §5 name fence not applicable",
        )

    return [
        i1,
        _report("I2", _CHECKS[1][1], "LOW", described, "FR description(s) carrying implementation detail"),
        _report("I3", _CHECKS[2][1], "LOW", folds, "fold candidate(s)"),
        _report("I4", _CHECKS[3][1], "MEDIUM", dupes, "duplicate FR ID(s)"),
        _basis_finding(rows),
    ]
