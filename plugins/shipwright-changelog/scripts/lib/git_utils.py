#!/usr/bin/env python3
"""Git utilities for changelog generation.

Provides:
- get_last_tag(): Find most recent semver tag
- get_commits_since(): Collect commits since a tag/ref
- parse_conventional_commit(): Parse commit message into type/scope/description
"""

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Optional


SEMVER_TAG_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+$")

CONVENTIONAL_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?P<breaking>!)?"
    r":\s*"
    r"(?P<description>.+)$"
)

BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:\s*", re.MULTILINE)

COMMIT_TYPES = {
    "feat", "fix", "refactor", "docs", "test", "chore",
    "style", "perf", "ci", "build",
}


@dataclass
class ParsedCommit:
    """A parsed conventional commit."""
    hash: str
    raw_message: str
    type: str = "other"
    scope: Optional[str] = None
    description: str = ""
    breaking: bool = False
    body: str = ""


def get_last_tag() -> Optional[str]:
    """Find the most recent semver tag."""
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            capture_output=True, text=True, encoding="utf-8",
        )
        for line in result.stdout.strip().splitlines():
            tag = line.strip()
            if SEMVER_TAG_PATTERN.match(tag):
                return tag
    except (FileNotFoundError, OSError):
        pass
    return None


def get_commits_since(ref: Optional[str] = None) -> list[dict]:
    """Get commits since ref (or all commits if ref is None).

    Returns list of {"hash": "abc123", "message": "feat: something"}.
    """
    cmd = ["git", "log", "--pretty=format:%H%n%B%n---COMMIT_END---"]
    if ref:
        cmd.append(f"{ref}..HEAD")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            print(json.dumps({
                "warning": "git log failed",
                "error_category": "transient",
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }), file=sys.stderr)
            return []
    except (FileNotFoundError, OSError) as exc:
        print(json.dumps({
            "warning": "git binary not available",
            "error_category": "permission",
            "exception": str(exc),
        }), file=sys.stderr)
        return []

    commits = []
    raw = result.stdout.strip()
    if not raw:
        return []  # Valid empty result: no commits since ref

    entries = raw.split("---COMMIT_END---")
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        lines = entry.splitlines()
        if lines:
            commit_hash = lines[0].strip()
            message = "\n".join(lines[1:]).strip()
            if commit_hash and len(commit_hash) >= 7:
                commits.append({"hash": commit_hash, "message": message})

    return commits


def parse_conventional_commit(commit_hash: str, message: str) -> ParsedCommit:
    """Parse a commit message into conventional commit parts."""
    lines = message.strip().splitlines()
    if not lines:
        return ParsedCommit(hash=commit_hash, raw_message=message)

    header = lines[0].strip()
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

    match = CONVENTIONAL_PATTERN.match(header)
    if not match:
        return ParsedCommit(
            hash=commit_hash,
            raw_message=message,
            description=header,
            body=body,
        )

    commit_type = match.group("type")
    if commit_type not in COMMIT_TYPES:
        commit_type = "other"

    breaking = bool(match.group("breaking")) or bool(BREAKING_FOOTER.search(body))

    return ParsedCommit(
        hash=commit_hash,
        raw_message=message,
        type=commit_type,
        scope=match.group("scope"),
        description=match.group("description"),
        breaking=breaking,
        body=body,
    )


def parse_all_commits(commits: list[dict]) -> list[ParsedCommit]:
    """Parse a list of raw commits into ParsedCommit objects."""
    return [
        parse_conventional_commit(c["hash"], c["message"])
        for c in commits
    ]


def suggest_version_bump(parsed: list[ParsedCommit], last_tag: Optional[str]) -> tuple[str, str]:
    """Suggest next version based on commit types.

    Returns (version, reason).
    """
    if not last_tag:
        return "0.1.0", "first release"

    # Parse current version
    tag = last_tag.lstrip("v")
    parts = tag.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    has_breaking = any(c.breaking for c in parsed)
    has_feat = any(c.type == "feat" for c in parsed)

    if has_breaking:
        if major == 0:
            return f"0.{minor + 1}.0", "breaking change (pre-1.0)"
        return f"{major + 1}.0.0", "breaking change"
    elif has_feat:
        return f"{major}.{minor + 1}.0", "new feature(s)"
    else:
        return f"{major}.{minor}.{patch + 1}", "bug fixes / maintenance"


def get_current_branch() -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, encoding="utf-8",
        )
        return result.stdout.strip()
    except (FileNotFoundError, OSError):
        return ""


# CLI interface for SKILL.md
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: git_utils.py <command> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "parse-commits":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--since", default=None)
        parser.add_argument("--format", default="json")
        args = parser.parse_args(sys.argv[2:])

        commits = get_commits_since(args.since)
        parsed = parse_all_commits(commits)

        output = [asdict(c) for c in parsed]
        print(json.dumps(output, indent=2))

    elif command == "last-tag":
        tag = get_last_tag()
        print(json.dumps({"tag": tag}))

    elif command == "suggest-version":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--since", default=None)
        args = parser.parse_args(sys.argv[2:])

        last_tag = args.since or get_last_tag()
        commits = get_commits_since(last_tag)
        parsed = parse_all_commits(commits)
        version, reason = suggest_version_bump(parsed, last_tag)
        print(json.dumps({"version": version, "reason": reason, "last_tag": last_tag}))
