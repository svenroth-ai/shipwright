"""Section file operations for /shipwright-plan.

Parsing lives in ``shared/scripts/lib/plan_manifest.py`` — one implementation
shared with the plan phase verifier, so the plugin's own gate and the
verifier's view cannot drift. This module keeps the file-system side (which
sections exist on disk, which declared ones are still missing) and the
``SectionManifestResult`` shape its callers already read.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

# parents[0]=lib, [1]=scripts, [2]=shipwright-plan, [3]=plugins, [4]=repo root.
# Appended, not inserted at 0: a library module must not shadow the importing
# plugin's own top-level modules (ADR-045).
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.append(str(_SHARED_LIB))

from plan_manifest import (  # noqa: E402
    SECTION_NAME_RE as SECTION_NAME_PATTERN,
    SectionEntry,
    parse_manifest,
    validate_dependency_order,
)

__all__ = [
    "SECTION_NAME_PATTERN",
    "SectionEntry",
    "SectionManifestResult",
    "get_missing_sections",
    "get_section_files",
    "get_sections_dir",
    "parse_section_manifest",
    "validate_dependency_order",
]


@dataclass
class SectionManifestResult:
    """Result of parsing SECTION_MANIFEST.

    ``sections`` and ``errors`` are unchanged; ``dependencies`` and ``entries``
    are additive so existing readers keep working untouched.
    """

    is_valid: bool
    sections: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    entries: list[SectionEntry] = field(default_factory=list)


def parse_section_manifest(plan_path: Path) -> SectionManifestResult:
    """Parse SECTION_MANIFEST block from plan.md."""
    parsed = parse_manifest(plan_path)
    return SectionManifestResult(
        is_valid=parsed.is_valid,
        sections=parsed.sections,
        errors=parsed.errors,
        dependencies=parsed.dependencies,
        entries=parsed.entries,
    )


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
