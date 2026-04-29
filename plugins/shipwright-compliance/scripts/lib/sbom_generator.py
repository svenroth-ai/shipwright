"""Software Bill of Materials (SBOM) generator.

Produces .shipwright/compliance/sbom.md with all open-source dependencies,
versions, and licenses.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib.mermaid import license_pie

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData, DependencyInfo


_COPYLEFT_LICENSES = {
    "GPL", "GPL-2.0", "GPL-3.0",
    "AGPL", "AGPL-3.0",
    "LGPL", "LGPL-2.1", "LGPL-3.0",
    "MPL-2.0",
}


def generate(data: ComplianceData) -> str:
    """Generate SBOM as Markdown string."""
    deps = data.dependencies

    runtime = [d for d in deps if d.dep_type == "runtime"]
    dev = [d for d in deps if d.dep_type == "dev"]
    copyleft = [d for d in deps if _is_copyleft(d.license)]

    # Collect unique licenses
    unique_licenses = sorted(set(d.license for d in deps)) if deps else []

    lines = [
        "# Software Bill of Materials (SBOM)",
        "",
        f"Generated: {data.timestamp}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Runtime dependencies | {len(runtime)} |",
        f"| Dev dependencies | {len(dev)} |",
        f"| Total packages | {len(deps)} |",
        f"| Unique licenses | {len(unique_licenses)} ({', '.join(unique_licenses) if unique_licenses else 'none'}) |",
        f"| Copyleft licenses | {len(copyleft)} |",
        "",
    ]

    if not deps:
        lines.append("_No dependency manifests found (package.json, pyproject.toml)._")
        return "\n".join(lines) + "\n"

    # License distribution
    lines.extend([
        "## License Distribution",
        "",
        license_pie(deps),
        "",
    ])

    # Runtime dependencies
    if runtime:
        lines.extend([
            "## Runtime Dependencies",
            "",
            "| Package | Version | License |",
            "|---------|---------|---------|",
        ])
        for d in sorted(runtime, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.license} |")
        lines.append("")

    # Dev dependencies
    if dev:
        lines.extend([
            "## Dev Dependencies",
            "",
            "| Package | Version | License |",
            "|---------|---------|---------|",
        ])
        for d in sorted(dev, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.license} |")
        lines.append("")

    # License compliance
    lines.extend([
        "## License Compliance",
        "",
    ])

    if copyleft:
        lines.extend([
            "**WARNING: Copyleft licenses detected.** These may restrict commercial use.",
            "",
            "| Package | Version | License | Risk |",
            "|---------|---------|---------|------|",
        ])
        for d in copyleft:
            lines.append(f"| {d.name} | {d.version} | {d.license} | Review required |")
        lines.append("")
    else:
        lines.append("No copyleft licenses detected. All dependencies are permissively licensed or unknown.")
        lines.append("")

    # Unknown licenses
    unknown = [d for d in deps if d.license == "unknown"]
    if unknown:
        lines.extend([
            "## Unknown Licenses",
            "",
            f"**{len(unknown)} packages** have unknown licenses. "
            "Install dependencies (`npm install` / `uv sync`) and regenerate to detect licenses.",
            "",
            "| Package | Version | Type |",
            "|---------|---------|------|",
        ])
        for d in sorted(unknown, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.dep_type} |")
        lines.append("")

    return "\n".join(lines) + "\n"


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate SBOM and write to .shipwright/compliance/sbom.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / COMPLIANCE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "sbom.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _is_copyleft(license_str: str) -> bool:
    """Check if a license is copyleft."""
    upper = license_str.upper()
    return any(cl in upper for cl in ("GPL", "AGPL", "LGPL", "MPL"))
