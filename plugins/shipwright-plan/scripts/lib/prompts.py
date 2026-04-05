"""Prompt template loading for /shipwright-plan.

Loads system/user prompts from the prompts/ directory for external LLM review.
"""

from pathlib import Path


def load_prompt(plugin_root: str | Path, prompt_dir: str, prompt_name: str) -> str:
    """Load a prompt template file.

    Args:
        plugin_root: Path to plugin root
        prompt_dir: Subdirectory in prompts/ (e.g., "plan_reviewer")
        prompt_name: File name (e.g., "system" or "user")

    Returns:
        Prompt content as string, or empty string if not found.
    """
    path = Path(plugin_root) / "prompts" / prompt_dir / prompt_name
    if not path.exists():
        # Try with .md extension
        path = path.with_suffix(".md")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_review_prompts(plugin_root: str | Path) -> tuple[str, str]:
    """Load system and user prompts for plan review.

    Returns:
        Tuple of (system_prompt, user_prompt_template)
    """
    system = load_prompt(plugin_root, "plan_reviewer", "system")
    user = load_prompt(plugin_root, "plan_reviewer", "user")
    return system, user


def load_iterate_review_prompts(plugin_root: str | Path) -> tuple[str, str]:
    """Load system and user prompts for iterate review.

    Falls back to sensible defaults if prompt files don't exist.

    Returns:
        Tuple of (system_prompt, user_prompt_template)
    """
    system = load_prompt(plugin_root, "iterate_reviewer", "system")
    user = load_prompt(plugin_root, "iterate_reviewer", "user")
    return system, user


def load_section_prompt(plugin_root: str | Path) -> str:
    """Load the section writer prompt template."""
    return load_prompt(plugin_root, "section_writer", "prompt.md")
