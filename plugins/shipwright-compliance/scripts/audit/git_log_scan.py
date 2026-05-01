"""B7 helper — reverse git-log scan with retention rules (plan v7 Step 5).

Walks ``git log`` between the most recent release tag and HEAD, classifies
each commit against the configured retention rules, and returns the
subset that should be checked against the event log.

Pure subprocess / git CLI — no GitPython, no extra dependencies. Failures
in any subprocess step return a structured ``ScanError`` rather than
crashing, so Group B's audit run keeps going.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CommitInfo:
    """A single commit considered by the reverse-scan."""

    sha: str
    author_email: str
    parent_count: int
    changed_paths: tuple[str, ...]

    def is_merge(self) -> bool:
        return self.parent_count > 1


@dataclass(frozen=True)
class ScanError:
    """Soft error wrapper — B7 reports as skip instead of crashing."""

    detail: str


def _run_git(repo: Path, args: list[str], timeout: int = 15) -> str:
    """Run ``git -C <repo> <args>`` and return stripped stdout.

    Raises ``RuntimeError`` on non-zero exit; the caller catches and
    converts that into a ``ScanError``.
    """
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} exited {result.returncode}: "
            f"{(result.stderr or '').strip()[:200]}"
        )
    return result.stdout


def is_git_repo(repo: Path) -> bool:
    try:
        _run_git(repo, ["rev-parse", "--is-inside-work-tree"], timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError, OSError):
        return False


def latest_release_tag(repo: Path, pattern: str) -> str | None:
    """Return the most recent annotated/lightweight tag matching *pattern*,
    or ``None`` when no matching tag exists.

    Uses ``git describe --tags --abbrev=0 --match <pattern>`` which prefers
    the closest tag reachable from HEAD. ``--abbrev=0`` forces the bare
    tag name (no commit hash suffix).
    """
    try:
        out = _run_git(
            repo,
            ["describe", "--tags", "--abbrev=0", "--match", pattern],
            timeout=10,
        )
    except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    tag = out.strip()
    return tag or None


def commits_since_tag(repo: Path, tag: str) -> list[str] | ScanError:
    """Return commit SHAs between ``<tag>..HEAD`` (newest first).

    Includes merge commits — Rule A's filter happens later via the
    per-commit ``parent_count`` check, not here.
    """
    try:
        out = _run_git(repo, ["log", "--pretty=format:%H", f"{tag}..HEAD"])
    except RuntimeError as exc:
        return ScanError(str(exc))
    return [line for line in out.splitlines() if line]


def commit_info(repo: Path, sha: str) -> CommitInfo | ScanError:
    """Collect (author email, parent count, changed paths) for one commit."""
    try:
        out = _run_git(
            repo,
            ["show", "--no-patch", "--pretty=format:%ae|%P", sha],
        )
    except RuntimeError as exc:
        return ScanError(str(exc))
    line = out.strip().splitlines()[0] if out.strip() else ""
    if "|" not in line:
        return ScanError(f"unparseable git show output for {sha}: {line!r}")
    email, parents = line.split("|", 1)
    parent_count = len(parents.split()) if parents.strip() else 0

    try:
        diff_out = _run_git(repo, ["show", "--name-only", "--pretty=format:", sha])
    except RuntimeError as exc:
        return ScanError(str(exc))
    paths = tuple(p for p in diff_out.splitlines() if p.strip())
    return CommitInfo(sha=sha, author_email=email,
                      parent_count=parent_count, changed_paths=paths)


def commit_is_within_path_prefixes(
    info: CommitInfo,
    prefixes: Iterable[str],
) -> bool:
    """True when EVERY path in the commit's diff sits under one of *prefixes*.

    Empty paths list → False (a no-change commit isn't conceptually
    "within prefixes"). Empty prefixes → False (Rule C disabled).
    """
    prefixes = tuple(p for p in prefixes if p)
    if not prefixes or not info.changed_paths:
        return False
    return all(
        any(path.startswith(prefix) for prefix in prefixes)
        for path in info.changed_paths
    )


@dataclass(frozen=True)
class FilterResult:
    """Outcome of applying retention rules to one commit."""

    commit: CommitInfo
    excluded: bool
    reason: str  # human-readable; empty when not excluded


def apply_retention_rules(
    info: CommitInfo,
    *,
    exclusions: dict,
    retention: dict,
) -> FilterResult:
    """Apply Rules A/B/C and return the result.

    Each rule respects two flags:
    - ``retention.rule_a/b/c`` (top-level on/off switch)
    - the corresponding sub-key under ``b7_exclusions``
    """
    rule_a_on = retention.get("rule_a", True)
    rule_b_on = retention.get("rule_b", True)
    rule_c_on = retention.get("rule_c", True)

    if rule_a_on and exclusions.get("exclude_merge_commits", True):
        if info.is_merge():
            return FilterResult(info, True, "merge commit (Rule A)")

    if rule_b_on:
        bot_authors = exclusions.get("exclude_authors", []) or []
        if any(bot in info.author_email for bot in bot_authors):
            return FilterResult(
                info, True,
                f"CI-bot author {info.author_email} (Rule B)",
            )

    if rule_c_on:
        prefixes = exclusions.get("exclude_path_prefixes", []) or []
        if commit_is_within_path_prefixes(info, prefixes):
            return FilterResult(
                info, True,
                f"diff fully under {prefixes} (Rule C)",
            )

    return FilterResult(info, False, "")
