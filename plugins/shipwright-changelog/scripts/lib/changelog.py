#!/usr/bin/env python3
"""Changelog generation in Keep-a-Changelog format.

Provides:
- categorize_commits(): Group parsed commits by changelog section
- generate_entry(): Create a changelog entry string
- update_changelog(): Splice an entry into CHANGELOG.md, preserving the rest
"""

import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

try:  # imported as a package module (``lib.changelog``)
    from ._shared_sections import load_changelog_sections
except ImportError:  # executed as a script (``python .../lib/changelog.py``)
    from _shared_sections import load_changelog_sections

# ONE implementation of the section predicates, shared with the release-time
# aggregator (`shared/scripts/changelog_sections.py`). See `_shared_sections`
# for why it is loaded by path rather than imported off `sys.path`.
#
# Resolved LAZILY, inside `update_changelog`, not at module scope: binding it
# here made a missing or stale `shared/` fail the whole `lib.changelog` import,
# taking down `categorize_commits` and `generate_entry`, which do not need the
# predicates at all. `ensure_shared_cache` is fail-open and re-mirrors
# `shared/` only when its sentinel is absent, so a cached copy predating this
# module is a reachable state. `load_changelog_sections` memoises, so the
# per-call cost is one dict lookup.


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


def _read_preserving(changelog_path: Path) -> tuple[str, str, str]:
    """Read the changelog, reporting its BOM and its line-ending convention.

    ``newline=""`` disables universal-newline translation so CRLF survives the
    round trip; a BOM is split off so it cannot blind the heading regexes (a
    BOM on line 0 made a first-line ``## [1.0.0]`` invisible, and the orphaned
    body was then deleted on the next run).
    """
    with changelog_path.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    bom = ""
    if text.startswith("﻿"):
        bom, text = "﻿", text[1:]
    return text, bom, "\r\n" if "\r\n" in text else "\n"


def _to_eol(text: str, eol: str) -> str:
    """Re-express `text` with the file's own line ending."""
    normalized = text.replace("\r\n", "\n")
    return normalized if eol == "\n" else normalized.replace("\n", eol)


def _write_atomic(changelog_path: Path, text: str) -> None:
    """Write via a temp file + os.replace.

    A plain write truncates first, so an interrupted write would leave the
    operator's entire history as a zero-length file — the exact loss this
    module exists to prevent. ``newline=""`` keeps the endings chosen above.
    """
    fd, tmp = tempfile.mkstemp(
        dir=str(changelog_path.parent), prefix=".changelog-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, changelog_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def update_changelog(
    changelog_path: Path,
    entry: str,
) -> str:
    """Insert `entry` into CHANGELOG.md, preserving everything already there.

    Creates the file with the standard header if it does not exist. Otherwise
    the entry is SPLICED into the text that was read — the file is never
    rebuilt from a fresh header, so no existing content can be dropped.
    Re-running with the same version replaces that version's section rather
    than appending a duplicate, so one version appears exactly once.

    Returns the full new content.

    Raises ValueError when the entry is not a released-version section, or when
    the file already holds more than one section for that version (which of
    them is authoritative is not knowable, so the caller must resolve it).
    """
    sections = load_changelog_sections()
    version = sections.entry_version(entry)

    if not changelog_path.exists():
        new_content = (
            CHANGELOG_HEADER + "## [Unreleased]\n\n" + entry.rstrip("\n") + "\n"
        )
        _write_atomic(changelog_path, new_content)
        return new_content

    content, bom, eol = _read_preserving(changelog_path)
    lines = content.splitlines(keepends=True)

    existing = sections.section_starts(lines, version)
    if len(existing) > 1:
        raise ValueError(
            f"{changelog_path} already contains {len(existing)} sections for "
            f"version {version}; refusing to guess which one to replace — "
            "remove the duplicates and re-run"
        )

    # Only the separators immediately around the spliced block are controlled.
    # Text outside it — trailing blank lines, the BOM, the line endings — is
    # carried through byte-for-byte. The one exception: appending at end of
    # file terminates a previously-unterminated last line.
    body = _to_eol(entry.rstrip("\n"), eol) + eol
    if existing:
        start = existing[0]
        head, tail = lines[:start], lines[sections.section_end(lines, start):]
    else:
        at = sections.insertion_index(lines)
        head, tail = lines[:at], lines[at:]

    if head and not head[-1].endswith("\n"):
        head = head[:-1] + [head[-1] + eol]
    prefix = eol if head and head[-1].strip() else ""
    suffix = eol if tail else ""

    new_content = bom + "".join(head + [prefix + body + suffix] + tail)
    _write_atomic(changelog_path, new_content)
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
        try:
            update_changelog(changelog_path, entry)
        except ValueError as exc:
            # Safe insertion was not possible. Stop with an actionable message
            # instead of writing something plausible over the operator's file.
            print(f"changelog: {exc}", file=sys.stderr)
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
            sys.exit(1)

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
