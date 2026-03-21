"""Parse SPLIT_MANIFEST from project-manifest.md.

Adapted from deep-project.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ManifestResult:
    """Result of parsing a project manifest."""

    is_valid: bool
    splits: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_manifest(manifest_path: Path) -> ManifestResult:
    """Parse SPLIT_MANIFEST block from project-manifest.md.

    Expected format at top of file:
    <!-- SPLIT_MANIFEST
    01-backend
    02-frontend
    END_MANIFEST -->
    """
    if not manifest_path.exists():
        return ManifestResult(is_valid=False, errors=[f"Manifest not found: {manifest_path}"])

    content = manifest_path.read_text(encoding="utf-8")

    # Extract SPLIT_MANIFEST block
    pattern = r"<!--\s*SPLIT_MANIFEST\s*\n(.*?)END_MANIFEST\s*-->"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return ManifestResult(
            is_valid=False,
            errors=["No SPLIT_MANIFEST block found. Expected <!-- SPLIT_MANIFEST ... END_MANIFEST -->"],
        )

    block = match.group(1).strip()
    if not block:
        return ManifestResult(is_valid=False, errors=["SPLIT_MANIFEST block is empty"])

    # Parse split names
    split_pattern = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
    splits = []
    errors = []

    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if not split_pattern.match(line):
            errors.append(f"Invalid split name: '{line}'. Expected format: NN-kebab-case (e.g., 01-backend)")
        else:
            splits.append(line)

    if errors:
        return ManifestResult(is_valid=False, splits=splits, errors=errors)

    if not splits:
        return ManifestResult(is_valid=False, errors=["No valid splits found in SPLIT_MANIFEST block"])

    # Check for duplicate numbers
    numbers = [s[:2] for s in splits]
    if len(numbers) != len(set(numbers)):
        return ManifestResult(is_valid=False, splits=splits, errors=["Duplicate split numbers found"])

    return ManifestResult(is_valid=True, splits=splits)
