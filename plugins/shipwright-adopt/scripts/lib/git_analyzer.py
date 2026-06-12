"""Git-log analysis for /shipwright-adopt: commits_total, major refactors, contributors."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


_REFACTOR_KEYWORDS_RE = re.compile(
    r"\b(refactor|migrate|restructure|breaking|rewrite|redesign|revamp|overhaul)\b",
    re.IGNORECASE,
)


def _run_git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            # WP7/F23: git emits UTF-8; without an explicit encoding the
            # subprocess reader thread decodes with the platform default
            # (cp1252 on Windows) and a Cyrillic/CJK/0x9D commit subject
            # raises UnicodeDecodeError in that thread — which escapes the
            # except below and crashes /shipwright-adopt. Pin UTF-8 and
            # replace undecodable bytes so analysis never aborts.
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def analyze_git(project_root: Path, max_refactor_commits: int = 10) -> dict[str, Any]:
    """Return git summary: total commits, major refactor commits, contributors."""
    # Total commits
    out = _run_git(["rev-list", "--count", "HEAD"], project_root)
    try:
        commits_total = int(out.strip()) if out.strip() else 0
    except ValueError:
        commits_total = 0

    # First commit date
    first_commit_iso = _run_git(
        ["log", "--reverse", "--format=%aI", "--max-count=1"],
        project_root,
    ).strip() or None

    # Contributors (unique author names)
    authors_raw = _run_git(["log", "--format=%an", "--no-merges"], project_root)
    contributors = sorted({a.strip() for a in authors_raw.splitlines() if a.strip()})

    # Major refactor commits: >5 files changed AND subject matches keyword regex
    log_raw = _run_git(
        ["log", "--no-merges", "--format=%H|%s|%ai|%an", "--numstat"],
        project_root,
    )
    major: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    files_changed = 0
    for raw in log_raw.splitlines():
        line = raw.strip()
        if not line:
            # End of a commit's stat block
            if current and files_changed >= 5 and _REFACTOR_KEYWORDS_RE.search(current["subject"]):
                current["files_changed"] = files_changed
                major.append(current)
            current = None
            files_changed = 0
            continue
        if "|" in line and line.count("|") >= 3:
            # Header line: hash|subject|date|author
            parts = line.split("|", 3)
            if current and files_changed >= 5 and _REFACTOR_KEYWORDS_RE.search(current["subject"]):
                current["files_changed"] = files_changed
                major.append(current)
            current = {
                "sha": parts[0],
                "subject": parts[1],
                "date": parts[2] if len(parts) > 2 else "",
                "author": parts[3] if len(parts) > 3 else "",
            }
            files_changed = 0
        else:
            # Numstat line: added\tdeleted\tpath
            if current and "\t" in line:
                files_changed += 1
    # Close last entry
    if current and files_changed >= 5 and _REFACTOR_KEYWORDS_RE.search(current["subject"]):
        current["files_changed"] = files_changed
        major.append(current)

    major.sort(key=lambda c: c.get("date", ""), reverse=True)

    return {
        "commits_total": commits_total,
        "first_commit": first_commit_iso,
        "contributors": contributors[:20],
        "contributors_total": len(contributors),
        "major_refactor_commits": major[:max_refactor_commits],
    }
