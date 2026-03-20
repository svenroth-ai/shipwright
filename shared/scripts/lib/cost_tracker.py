"""Track estimated tokens and API calls per section.

This is a data writer — it records values that the SKILL.md flow
provides. It does NOT measure actual token usage (Claude Code doesn't
expose this to plugins). Values are estimates based on conversation
turns and known patterns.

Data is stored in shipwright_build_config.json under each section's
entry.
"""

from pathlib import Path
from typing import Any

from .config import read_config, write_config


def record_section_cost(
    project_root: str | Path,
    section_name: str,
    estimated_tokens: int,
    estimated_api_calls: int,
) -> dict[str, Any]:
    """Record cost estimates for a section in the build config.

    Args:
        project_root: Path to the target project root.
        section_name: Name of the section (e.g. "01-auth-setup").
        estimated_tokens: Estimated total tokens used.
        estimated_api_calls: Estimated number of LLM API calls.

    Returns:
        The updated section entry.
    """
    config = read_config("build", project_root)
    sections = config.setdefault("sections", [])

    # Find or create section entry
    section = next((s for s in sections if s["name"] == section_name), None)
    if section is None:
        section = {"name": section_name}
        sections.append(section)

    section["estimated_tokens_used"] = estimated_tokens
    section["estimated_api_calls"] = estimated_api_calls

    write_config("build", project_root, config)
    return section


def get_project_cost_summary(project_root: str | Path) -> dict[str, int]:
    """Aggregate cost estimates across all sections.

    Returns:
        Dict with total_tokens and total_api_calls.
    """
    config = read_config("build", project_root)
    sections = config.get("sections", [])

    return {
        "total_tokens": sum(s.get("estimated_tokens_used", 0) for s in sections),
        "total_api_calls": sum(s.get("estimated_api_calls", 0) for s in sections),
        "section_count": len(sections),
    }
