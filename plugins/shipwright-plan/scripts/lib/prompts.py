"""Prompt template loading for /shipwright-plan.

Loads section-writer prompts from the plugin's prompts/ directory.

External-review prompts (plan_reviewer, iterate_reviewer) live in
``shared/scripts/lib/external_review_prompts.py`` and load from
``{plugin_root}/prompts/plan_reviewer/`` (plan-mode) or
``shared/prompts/iterate_reviewer/`` (iterate-mode).
"""

from pathlib import Path


def load_prompt(plugin_root: str | Path, prompt_dir: str, prompt_name: str) -> str:
    """Load a prompt template file.

    Args:
        plugin_root: Path to plugin root
        prompt_dir: Subdirectory in prompts/ (e.g., "section_writer")
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


def load_section_prompt(plugin_root: str | Path) -> str:
    """Load the section writer prompt template."""
    return load_prompt(plugin_root, "section_writer", "prompt.md")
