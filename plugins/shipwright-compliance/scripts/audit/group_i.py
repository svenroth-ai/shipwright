"""Group I — Requirement Hygiene (detective-only).

Reports FR rows that drift from `shared/fr-authoring.md`: implementation detail
leaking into a requirement's name or description, change-deltas minted as their
own requirement, and duplicate FR IDs.

- I1 — FR name carries a verb / symbol / path / ADR number / iterate slug
- I2 — FR description carries implementation detail
- I3 — FR only describes a change to another FR (fold candidate)
- I4 — the same FR ID used twice within one split

**Advisory by construction, not by luck.** The three prose checks (I1/I2/I3)
never emit ``status="fail"``, because a failing finding feeds
``AuditReport.any_fail`` — which drives ``run_audit``'s exit code and the
compliance dashboard verdict. Legacy specs are expected to carry historical
violations, and the requirement is that they must not redden CI while a spec
cleans up gradually. The counts and IDs still ride in ``detail``, so no signal
is lost; only the verdict is left alone.

I4 is the exception and DOES fail: two rows claiming one FR ID is an objective
defect, not a style opinion. No finding is ever HIGH.

**Deliberately does not reuse the shared FR parser.** ``drift_parsers`` and the
RTM collector are the *authoritative* requirement readers feeding traceability;
they intentionally collapse the table to one semantic body field. Hygiene needs
the Name and Description cells kept apart, so this module does its own
header-driven scan. Nothing downstream consumes it — a scanning mistake here can
only produce a wrong advisory line, never a traceability defect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY, Finding

# Detectors live in the pure sibling module; re-exported here so callers and
# tests keep a single entry point (`group_i.name_violations`, …).
from scripts.audit.group_i_detectors import (
    description_violations,
    is_fold_candidate,
    name_violations,
)


_FR_ID_RE = re.compile(r"^FR-\d+\.\d+$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


# ---------------------------------------------------------------------------
# Row scanner — header-driven so every table shape is read correctly
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


def _split_cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [c.strip() for c in _UNESCAPED_PIPE_RE.split(inner)]


def _column_map(cells: list[str]) -> tuple[int | None, int | None] | None:
    """Map a header row to ``(name_idx, description_idx)``.

    Greenfield tables carry a single ``Requirement`` sentence and no separate
    name — that column is treated as the description so §1 still applies, and
    the §5 name fence is skipped rather than misapplied. The ``Source`` column
    is never mapped: file paths are legitimate there.
    """
    low = [c.lower() for c in cells]
    if not low or low[0] != "id":
        return None
    name_idx = low.index("name") if "name" in low else None
    if "description" in low:
        return name_idx, low.index("description")
    for alias in ("requirement", "name"):
        if alias in low:
            return None, low.index(alias)
    return None


def _scan_one_spec(path: Path, split: str, spec_path: str) -> list[FrRow]:
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    rows: list[FrRow] = []
    mapping: tuple[int | None, int | None] | None = None
    in_removed = False
    removed_level = 0

    for line in content.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if heading.group(2).strip().lower().startswith("removed requirements"):
                in_removed, removed_level = True, level
            elif in_removed and level <= removed_level:
                in_removed = False
            mapping = None  # a new section starts a new table
            continue
        if not line.lstrip().startswith("|"):
            continue

        cells = _split_cells(line)
        header = _column_map(cells)
        if header is not None:
            mapping = header
            continue
        if mapping is None or not cells or not _FR_ID_RE.match(cells[0]):
            continue

        name_idx, desc_idx = mapping
        rows.append(FrRow(
            id=cells[0],
            name=cells[name_idx] if name_idx is not None and name_idx < len(cells) else "",
            description=cells[desc_idx] if desc_idx is not None and desc_idx < len(cells) else "",
            split=split,
            spec_path=spec_path,
            retired=in_removed,
        ))
    return rows


def scan_fr_rows(project_root: Path, *, include_retired: bool = False) -> list[FrRow]:
    """FR rows under ``.shipwright/planning/<split>/spec.md``.

    Live rows only by default — that is what the prose checks lint. Pass
    ``include_retired=True`` for the I4 number-reuse check, which must see
    ``### Removed Requirements`` rows too.
    """
    planning = project_root / ".shipwright" / "planning"
    if not planning.is_dir():
        return []
    rows: list[FrRow] = []
    for split_dir in sorted(p for p in planning.iterdir() if p.is_dir()):
        spec = split_dir / "spec.md"
        if spec.is_file():
            rel = f".shipwright/planning/{split_dir.name}/spec.md"
            rows.extend(_scan_one_spec(spec, split_dir.name, rel))
    return rows if include_retired else [r for r in rows if not r.retired]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

_PREVIEW_CAP = 5

_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("I1", "FR name carries implementation detail", "LOW"),
    ("I2", "FR description carries implementation detail", "LOW"),
    ("I3", "FR is a change-delta, not a capability", "LOW"),
    ("I4", "Duplicate FR ID within a split", "MEDIUM"),
)

#: I1/I2/I3 are prose heuristics over legacy specs, so they report WITHOUT
#: ``status="fail"``: a failing finding feeds ``AuditReport.any_fail``, which
#: flips ``run_audit``'s exit code and the dashboard verdict. The requirement is
#: explicit that existing violations must not redden CI — a spec should be able
#: to clean up gradually. The count and IDs still ride in ``detail``, so the
#: signal is fully preserved; only the verdict is left alone.
#:
#: I4 is excluded: a duplicate FR ID is an objective defect (two rows claiming
#: one identity), never legacy style noise, so it fails for real.
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


def run(
    project_root: Path,
    _config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run every I-group check. Absent specs SKIP rather than fail."""
    rows = scan_fr_rows(project_root)
    if not rows:
        return [
            _finding(cid, name, sev, "skip", "no FR rows found — nothing to audit")
            for cid, name, sev in _CHECKS
        ]

    described = [
        f"{r.id} ({'/'.join(description_violations(r.description))})"
        for r in rows if description_violations(r.description)
    ]
    folds = [r.id for r in rows if is_fold_candidate(r.description)]

    # I4 must see retired rows: §4 forbids reusing a removed FR's number.
    all_rows = scan_fr_rows(project_root, include_retired=True)
    seen: dict[tuple[str, str], int] = {}
    for r in all_rows:
        seen[(r.split, r.id)] = seen.get((r.split, r.id), 0) + 1
    dupes = sorted({fid for (_split, fid), n in seen.items() if n > 1})

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
    ]
