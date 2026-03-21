"""Section tracking for /shipwright-build.

Reads section manifest from plan and tracks completion state.
"""

import json
import re
from pathlib import Path
from typing import Any


SECTION_NAME_PATTERN = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_valid_section_name(name: str) -> bool:
    """Check if name matches section pattern (NN-kebab-case)."""
    return bool(SECTION_NAME_PATTERN.match(name))


def extract_section_name(file_path: str | Path) -> str | None:
    """Extract section name from a section file path.

    Example: sections/01-auth.md → 01-auth
    """
    path = Path(file_path)
    stem = path.stem
    if is_valid_section_name(stem):
        return stem
    return None


def get_section_scope(section_name: str) -> str:
    """Extract scope from section name (without number prefix).

    Example: 01-auth → auth, 03-user-dashboard → user-dashboard
    """
    return section_name[3:]  # Skip "NN-"


def load_section_states(project_root: str | Path) -> dict[str, Any]:
    """Load section states from shipwright_build_config.json."""
    config_path = Path(project_root) / "shipwright_build_config.json"
    if not config_path.exists():
        return {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return {s["name"]: s for s in config.get("sections", [])}
    except (json.JSONDecodeError, KeyError):
        return {}
