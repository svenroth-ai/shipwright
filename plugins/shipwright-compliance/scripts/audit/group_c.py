"""Group C — Planning internal coherence (plan v7 Option Z).

Every check here is a preventive-rerun of an iterate-12 verifier. Specs
and plans can drift after ``/shipwright-plan`` completes (manual edits,
force-pushes); this group catches that drift on demand.

Mapping:
- C1 ``check_design_fr_coverage``       — every FR in spec → plan section or design manifest
- C2 ``check_fr_orphans_in_plan``       — every FR-ID in plan.md → spec.md
- C3 ``check_section_files_match_manifest`` — plan SECTION_MANIFEST ↔ section files
- C4 ``check_section_id_validity``      — section IDs unique, zero-padded, valid depends_on
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
    # (check_fn_name, check_id, human_name)
    ("check_design_fr_coverage", "C1", "Spec FR → plan/design coverage"),
    ("check_fr_orphans_in_plan", "C2", "Plan FR → spec"),
    ("check_section_files_match_manifest", "C3", "SECTION_MANIFEST ↔ section files"),
    ("check_section_id_validity", "C4", "Section-ID structural validity"),
)


def run(
    project_root: Path,
    _config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run every C-group check and adapt the CheckResults to Findings."""
    checks = import_iterate12_checks()
    findings: list[Finding] = []

    for fn_name, check_id, human_name in _CHECK_TO_ID:
        fn = checks[fn_name]
        try:
            result = fn(project_root)
        except Exception as exc:  # noqa: BLE001 — one broken check shouldn't drop the group
            findings.append(Finding(
                group="C", check_id=check_id, name=human_name,
                severity="HIGH", source=SOURCE_PREVENTIVE_RERUN, status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
            continue
        finding = check_result_to_finding(
            result, group="C", check_id=check_id,
            source=SOURCE_PREVENTIVE_RERUN,
            suggested_iterate_cmd=(
                f"/shipwright-iterate --type change "
                f"\"reconcile {check_id} ({human_name}) "
                f"— see .shipwright/compliance/audit-report.md\""
            ),
        )
        finding.name = human_name
        findings.append(finding)

    return findings
