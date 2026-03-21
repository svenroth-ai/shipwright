"""Section file operations for /shipwright-plan.

Handles parsing SECTION_MANIFEST from plan.md and tracking section completion.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


SECTION_MANIFEST_PATTERN = re.compile(
    r"<!--\s*SECTION_MANIFEST\s*\n(.*?)END_MANIFEST\s*-->",
    re.DOTALL,
)
SECTION_NAME_PATTERN = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class SectionManifestResult:
    """Result of parsing SECTION_MANIFEST."""

    is_valid: bool
    sections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_section_manifest(plan_path: Path) -> SectionManifestResult:
    """Parse SECTION_MANIFEST block from plan.md."""
    if not plan_path.exists():
        return SectionManifestResult(is_valid=False, errors=[f"Plan not found: {plan_path}"])

    content = plan_path.read_text(encoding="utf-8")
    match = SECTION_MANIFEST_PATTERN.search(content)

    if not match:
        return SectionManifestResult(
            is_valid=False,
            errors=["No SECTION_MANIFEST block found in plan.md"],
        )

    block = match.group(1).strip()
    if not block:
        return SectionManifestResult(is_valid=False, errors=["SECTION_MANIFEST block is empty"])

    sections = []
    errors = []

    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if not SECTION_NAME_PATTERN.match(line):
            errors.append(f"Invalid section name: '{line}'")
        else:
            sections.append(line)

    if errors:
        return SectionManifestResult(is_valid=False, sections=sections, errors=errors)

    if not sections:
        return SectionManifestResult(is_valid=False, errors=["No valid sections found"])

    return SectionManifestResult(is_valid=True, sections=sections)


def get_sections_dir(planning_dir: Path) -> Path:
    """Get the sections directory path."""
    return planning_dir / "sections"


def get_section_files(planning_dir: Path) -> list[str]:
    """Get list of existing section files."""
    sections_dir = get_sections_dir(planning_dir)
    if not sections_dir.exists():
        return []
    return sorted([
        f.stem for f in sections_dir.iterdir()
        if f.is_file() and f.suffix == ".md" and SECTION_NAME_PATTERN.match(f.stem)
    ])


def get_missing_sections(planning_dir: Path, declared: list[str]) -> list[str]:
    """Get sections declared in manifest but not yet written."""
    existing = get_section_files(planning_dir)
    return [s for s in declared if s not in existing]
