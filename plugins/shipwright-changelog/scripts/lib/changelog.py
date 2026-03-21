#!/usr/bin/env python3
"""Changelog generation in Keep-a-Changelog format.

Provides:
- categorize_commits(): Group parsed commits by changelog section
- generate_entry(): Create a changelog entry string
- update_changelog(): Prepend entry to CHANGELOG.md
"""

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional


# Map commit types to changelog sections (in display order)
TYPE_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "perf": "Changed",
    "docs": "Documentation",
    "chore": "Maintenance",
    "ci": "Maintenance",
    "build": "Maintenance",
    "style": "Maintenance",
    "test": "Testing",
    "other": "Other",
}

SECTION_ORDER = [
    "Breaking Changes",
    "Added",
    "Fixed",
    "Changed",
    "Documentation",
    "Testing",
    "Maintenance",
    "Other",
]

CHANGELOG_HEADER = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

"""


def categorize_commits(parsed_commits: list[dict]) -> dict[str, list[str]]:
    """Group commits by changelog section.

    Args:
        parsed_commits: List of ParsedCommit dicts (from git_utils).

    Returns:
        Dict mapping section name to list of formatted entries.
    """
    sections: dict[str, list[str]] = defaultdict(list)

    for commit in parsed_commits:
        commit_type = commit.get("type", "other")
        scope = commit.get("scope")
        description = commit.get("description", commit.get("raw_message", ""))
        breaking = commit.get("breaking", False)

        # Format entry
        if scope:
            entry = f"{commit_type}({scope}): {description}"
        else:
            entry = f"{commit_type}: {description}"

        # Categorize
        if breaking:
            sections["Breaking Changes"].append(entry)

        section = TYPE_TO_SECTION.get(commit_type, "Other")
        sections[section].append(entry)

    return dict(sections)


def generate_entry(
    version: str,
    sections: dict[str, list[str]],
    release_date: Optional[str] = None,
) -> str:
    """Generate a changelog entry string.

    Args:
        version: Version string (e.g., "1.2.0")
        sections: Dict from categorize_commits()
        release_date: ISO date string (defaults to today)

    Returns:
        Formatted changelog entry.
    """
    if not release_date:
        release_date = date.today().isoformat()

    lines = [f"## [{version}] - {release_date}", ""]

    for section_name in SECTION_ORDER:
        entries = sections.get(section_name, [])
        if not entries:
            continue
        lines.append(f"### {section_name}")
        for entry in entries:
            lines.append(f"- {entry}")
        lines.append("")

    return "\n".join(lines)


def update_changelog(
    changelog_path: Path,
    entry: str,
) -> str:
    """Prepend a new entry to CHANGELOG.md.

    Creates the file with standard header if it doesn't exist.
    Inserts after the header and any [Unreleased] section.

    Returns the full new content.
    """
    if changelog_path.exists():
        content = changelog_path.read_text(encoding="utf-8")
    else:
        content = CHANGELOG_HEADER + "## [Unreleased]\n\n"

    # Find insertion point: after [Unreleased] section
    unreleased_marker = "## [Unreleased]"
    if unreleased_marker in content:
        idx = content.index(unreleased_marker)
        # Find end of Unreleased section (next ## or end)
        rest = content[idx + len(unreleased_marker):]
        next_section = rest.find("\n## [")
        if next_section == -1:
            # No existing versions — append after Unreleased
            new_content = (
                content[:idx]
                + unreleased_marker + "\n\n"
                + entry + "\n"
            )
        else:
            insert_at = idx + len(unreleased_marker) + next_section + 1
            new_content = (
                content[:insert_at]
                + entry + "\n"
                + content[insert_at:]
            )
    else:
        # No Unreleased section — prepend after header
        new_content = CHANGELOG_HEADER + "## [Unreleased]\n\n" + entry + "\n"

    changelog_path.write_text(new_content, encoding="utf-8")
    return new_content


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: changelog.py <command> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "generate":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--version", required=True)
        parser.add_argument("--commits-json", required=True, help="Path to parsed commits JSON")
        parser.add_argument("--changelog-path", default="CHANGELOG.md")
        parser.add_argument("--date", default=None)
        args = parser.parse_args(sys.argv[2:])

        commits_path = Path(args.commits_json)
        parsed = json.loads(commits_path.read_text(encoding="utf-8"))

        sections = categorize_commits(parsed)
        entry = generate_entry(args.version, sections, args.date)

        changelog_path = Path(args.changelog_path)
        update_changelog(changelog_path, entry)

        print(json.dumps({
            "success": True,
            "version": args.version,
            "sections": {k: len(v) for k, v in sections.items()},
            "changelog_path": str(changelog_path),
            "entry": entry,
        }, indent=2))

    elif command == "categorize":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--commits-json", required=True)
        args = parser.parse_args(sys.argv[2:])

        parsed = json.loads(Path(args.commits_json).read_text(encoding="utf-8"))
        sections = categorize_commits(parsed)
        print(json.dumps(sections, indent=2))
