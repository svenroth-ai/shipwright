"""Group F — ADR structural integrity (plan v7 Option Z).

Structural checks only (sequential IDs, valid status, supersession refs).
Content quality is handled by Phase-Quality Q1 (Tier-2 "ADR substance"),
so F and Q1 scan different axes and do not overlap.

Every check is a preventive-rerun of an iterate-12 common.py verifier.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.audit.audit_adapters import (
    SOURCE_PREVENTIVE_RERUN,
    Finding,
    check_result_to_finding,
    import_iterate12_checks,
)


_CHECK_TO_ID: tuple[tuple[str, str, str], ...] = (
    ("check_adr_ids_sequential", "F1", "ADR IDs unique + sequential"),
    ("check_adr_status_valid", "F2", "ADR Status in valid enum"),
    ("check_adr_supersession_exists", "F3", "Superseded ADRs reference a replacement"),
)


def run(
    project_root: Path,
    _config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    checks = import_iterate12_checks()
    findings: list[Finding] = []

    for fn_name, check_id, human_name in _CHECK_TO_ID:
        fn = checks[fn_name]
        try:
            result = fn(project_root)
        except Exception as exc:  # noqa: BLE001
            findings.append(Finding(
                group="F", check_id=check_id, name=human_name,
                severity="HIGH", source=SOURCE_PREVENTIVE_RERUN, status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
            continue
        finding = check_result_to_finding(
            result, group="F", check_id=check_id,
            source=SOURCE_PREVENTIVE_RERUN,
            # F1 (gap) is most actionable via a manual ADR fix, not iterate.
            suggested_iterate_cmd=None,
        )
        finding.name = human_name
        findings.append(finding)

    return findings
