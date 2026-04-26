"""Traceability-category checks (Phase-Quality PR 3).

Implements T1 and T2 — the Spec ↔ RTM mapping invariants that catch
"requirement drifted past the matrix" bugs.

- **T1** (Tier-1, FAIL): every FR declared in a ``.shipwright/planning/*/spec.md`` is
  present in ``compliance/traceability-matrix.md``. Catches the exact
  gap that the plan names in § 1 ("FR-7 in spec.md, not in RTM").
- **T2** (Tier-2, WARN): no RTM rows reference FR ids that don't exist
  in any spec. Heuristic only — test renames, partial checkouts or
  superseded FRs are common FPs, so the finding carries
  ``provenance: unverified_marker``.

Both checks delegate FR-table parsing to
``lib.drift_parsers.collect_requirements_from_planning`` so the RTM
parser and the spec parser can never drift apart.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import collect_requirements_from_planning  # noqa: E402
from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    make_finding,
)


T1_NAME = "T1 every spec FR is mapped in RTM"
T2_NAME = "T2 no orphan FR rows in RTM"

T1_REMEDIATION = (
    "Add the missing FR rows to compliance/traceability-matrix.md "
    "(regenerate via `uv run update_compliance.py --phase <phase>`)."
)
T2_REMEDIATION = (
    "Either remove the orphan RTM rows (FR was deleted) or re-add the "
    "FR to .shipwright/planning/<split>/spec.md. Tier-2 heuristic — WARN only."
)

# Matches a row reference like "| FR-03.14 | ..." or the id embedded in a
# markdown link "[FR-03.14](..#fr-0314)". Covers both shapes the existing
# ``rtm_generator.py`` uses.
_RTM_FR_RE = re.compile(r"\bFR-\d+\.\d+\b")


def _rtm_fr_ids(project_root: Path) -> tuple[set[str], Path | None]:
    rtm = project_root / "compliance" / "traceability-matrix.md"
    if not rtm.exists():
        return set(), None
    try:
        text = rtm.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set(), rtm
    return set(_RTM_FR_RE.findall(text)), rtm


def check_t1_all_spec_frs_mapped(project_root: Path) -> dict[str, Any]:
    """T1 — every FR from planning specs is present in the RTM.

    SKIP semantics:
    - No .shipwright/planning/ directory → SKIP (project hasn't reached plan phase).
    - .shipwright/planning/ present but no FR rows → SKIP (empty spec).
    - RTM missing → FAIL (spec exists, RTM must follow).
    """
    requirements = collect_requirements_from_planning(project_root)
    if not requirements:
        return make_finding(
            "T1", STATUS_SKIP,
            "no FRs found under .shipwright/planning/*/spec.md — nothing to map",
            name=T1_NAME,
        )

    rtm_ids, rtm_path = _rtm_fr_ids(project_root)
    if rtm_path is None:
        return make_finding(
            "T1", STATUS_FAIL,
            f"compliance/traceability-matrix.md missing "
            f"({len(requirements)} FR(s) unmapped)",
            name=T1_NAME,
            remediation=T1_REMEDIATION,
        )

    spec_ids = {r.id for r in requirements}
    orphans = sorted(spec_ids - rtm_ids)
    if orphans:
        preview = ", ".join(orphans[:5])
        suffix = f" (+{len(orphans) - 5} more)" if len(orphans) > 5 else ""
        return make_finding(
            "T1", STATUS_FAIL,
            f"{len(orphans)} FR(s) not mapped in RTM: {preview}{suffix}",
            name=T1_NAME,
            remediation=T1_REMEDIATION,
        )

    return make_finding(
        "T1", STATUS_PASS,
        f"all {len(spec_ids)} FR(s) present in RTM",
        name=T1_NAME,
    )


def check_t2_no_orphan_rtm_rows(project_root: Path) -> dict[str, Any]:
    """T2 — RTM references no FR ids that are absent from every spec.

    Tier-2. Never FAIL (plan § 7 R12 — FR renames and partial checkouts
    produce FPs). Always WARN on mismatch so reviewers can look without
    the audit blocking.
    """
    requirements = collect_requirements_from_planning(project_root)
    if not requirements:
        return make_finding(
            "T2", STATUS_SKIP,
            "no spec FRs found — no baseline to detect orphans",
            name=T2_NAME,
            provenance="unverified_marker",
        )

    rtm_ids, rtm_path = _rtm_fr_ids(project_root)
    if rtm_path is None:
        return make_finding(
            "T2", STATUS_SKIP,
            "compliance/traceability-matrix.md missing — T1 covers this",
            name=T2_NAME,
        )

    spec_ids = {r.id for r in requirements}
    orphans = sorted(rtm_ids - spec_ids)
    if not orphans:
        return make_finding(
            "T2", STATUS_PASS,
            f"no orphan rows ({len(rtm_ids)} RTM FR(s) all backed by specs)",
            name=T2_NAME,
        )

    preview = ", ".join(orphans[:5])
    suffix = f" (+{len(orphans) - 5} more)" if len(orphans) > 5 else ""
    return make_finding(
        "T2", STATUS_WARN,
        f"{len(orphans)} orphan RTM row(s) not in any spec: {preview}{suffix}",
        name=T2_NAME,
        remediation=T2_REMEDIATION,
        provenance="unverified_marker",
    )


_PHASE_TO_CHECKS: dict[str, tuple[str, ...]] = {
    "project": ("T1", "T2"),
    "iterate": ("T1", "T2"),
}


def run(phase: str, project_root: Path) -> list[dict[str, Any]]:
    """Dispatch per the Plugin-Coverage table (plan § 5.1)."""
    checks = _PHASE_TO_CHECKS.get(phase)
    if not checks:
        return []
    findings: list[dict[str, Any]] = []
    for check_id in checks:
        if check_id == "T1":
            findings.append(check_t1_all_spec_frs_mapped(project_root))
        elif check_id == "T2":
            findings.append(check_t2_no_orphan_rtm_rows(project_root))
    return findings


__all__ = [
    "check_t1_all_spec_frs_mapped",
    "check_t2_no_orphan_rtm_rows",
    "run",
]
