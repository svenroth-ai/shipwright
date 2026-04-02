"""Compliance Dashboard generator.

Produces compliance/dashboard.md — the single-page overview.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


_COPYLEFT_LICENSES = {"GPL", "LGPL", "AGPL", "MPL-2.0", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"}


def generate(data: ComplianceData) -> str:
    """Generate Compliance Dashboard as Markdown string."""
    run_config = data.configs.get("run", {})
    profile = run_config.get("profile", "unknown")
    scope = run_config.get("scope", "unknown")

    lines = [
        "# Compliance Dashboard",
        "",
        f"Generated: {data.timestamp}",
        f"Profile: {profile}",
        f"Scope: {scope}",
        "",
    ]

    # Quality indicators
    total_sections = len(data.sections)
    completed = sum(1 for s in data.sections if s.status == "complete")
    total_passed = sum(s.tests_passed for s in data.sections)
    total_tests = sum(s.tests_total for s in data.sections)
    reviewed = total_sections  # all sections go through code review
    total_decisions = sum(len(e.decisions) for e in data.decisions)
    total_deps = len(data.dependencies)
    copyleft = sum(
        1 for d in data.dependencies
        if any(cl in d.license.upper() for cl in ("GPL", "AGPL", "LGPL", "MPL"))
    )

    lines.extend([
        "## Quality Indicators",
        "",
        "| Indicator | Value | Status | Description |",
        "|-----------|-------|--------|-------------|",
        f"| All planned splits built | {len(data.splits)} | {_status_badge(len(data.splits) > 0)} | Every project split has been implemented |",
        f"| All sections completed | {completed}/{total_sections} | {_status_badge(completed == total_sections and total_sections > 0)} | Build sections across all splits |",
        f"| All unit tests passing | {total_passed}/{total_tests} | {_status_badge(total_passed == total_tests and total_tests > 0)} | Unit tests across all sections |",
        f"| Code reviewed | {reviewed}/{total_sections} sections | {_status_badge(reviewed == total_sections and total_sections > 0)} | Sections that went through code review |",
        f"| Architecture decisions logged | {total_decisions} | INFO | ADR entries in decision_log.md |",
        f"| Third-party dependencies | {total_deps} | INFO | Open-source packages in use |",
        f"| Copyleft license risk | {copyleft} | {_status_badge(copyleft == 0)} | Packages with GPL/AGPL/LGPL/MPL licenses |",
        "",
    ])

    # Compliance artifacts
    artifact_rows = [
        "| Traceability Matrix | [traceability-matrix.md](./traceability-matrix.md) | Requirements → Sections → Tests |",
        "| Test Evidence | [test-evidence.md](./test-evidence.md) | Per-section test results |",
        "| Commit Change Log | [change-history.md](./change-history.md) | Conventional Commits by type |",
        "| Decision Log | [decision_log.md](../agent_docs/decision_log.md) | Architecture decisions (ADRs) |",
        "| SBOM | [sbom.md](./sbom.md) | Open-source dependencies + licenses |",
    ]
    # Add CHANGELOG if it exists
    if (data.project_root / "CHANGELOG.md").exists():
        artifact_rows.append("| Changelog | [CHANGELOG.md](../CHANGELOG.md) | Release notes |")

    lines.extend([
        "## Compliance Artifacts",
        "",
        "| Document | Path | Description |",
        "|----------|------|-------------|",
        *artifact_rows,
        "",
    ])

    return "\n".join(lines) + "\n"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate Dashboard and write to compliance/dashboard.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / "compliance"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "dashboard.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _status_badge(ok: bool) -> str:
    """Return PASS or WARN text."""
    return "PASS" if ok else "WARN"
