"""B7 helper — reverse git-log scan with retention rules (plan v7 Step 5).

Walks ``git log`` between the most recent release tag and HEAD, classifies
each commit against the configured retention rules, and returns the
subset that should be checked against the event log.

Pure subprocess / git CLI — no GitPython, no extra dependencies. Failures
in any subprocess step return a structured ``ScanError`` rather than
crashing, so Group B's audit run keeps going.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Loose ``Run-ID:`` trailer match — the same convention
# ``audit_staleness.find_snapshot_commit`` keys on (a ``Run-ID: <run-id>``
# line anywhere in the commit message, not strict git-trailer parsing).
_RUN_ID_TRAILER_RE = re.compile(r"(?im)^[ \t]*Run-ID:[ \t]*(\S+)[ \t]*$")

# Conventional-Commit ``type[(scope)][!]:`` header — group 1 is the type.
_CONVENTIONAL_TYPE_RE = re.compile(r"^([A-Za-z]+)(?:\([^)]*\))?!?:")

# Non-functional Conventional-Commit types: repo maintenance with no
# product / RTM footprint. Rule E excludes these from B7 by default (they need
# no work_completed event), so a direct ``ci``/``docs``/``chore`` commit is not
# a recurring B7 entry. Functional types (feat, fix, perf, refactor) are NOT
# here — a feature/fix that bypassed the iterate flow is real drift B7 keeps
# surfacing. Opt out per project via ``b7_exclusions.exclude_nonfunctional_types
# = false`` (restores the old flag-everything stance) or override the set via
# ``b7_exclusions.nonfunctional_types``.
# (iterate-2026-06-05-b7-exclude-nonfunctional — supersedes the narrow-Rule-D
# decision of B, 2026-06-02-compliance-detective-realign.)
_NONFUNCTIONAL_TYPES = frozenset({"build", "chore", "ci", "docs", "style", "test"})


@dataclass(frozen=True)
class CommitInfo:
    """A single commit considered by the reverse-scan."""

    sha: str
    author_email: str
    parent_count: int
    changed_paths: tuple[str, ...]
    subject: str = ""  # commit subject (first line / conventional-commit header)

    def is_merge(self) -> bool:
        return self.parent_count > 1

    def is_release_commit(self) -> bool:
        """True for a changelog/release-phase commit (``chore(release): ...``).

        The release phase (/shipwright-changelog) produces this commit BY DESIGN
        (version bump + changelog + dashboards); it is a tracked SDLC-phase
        output, NOT iterate work, so it carries no work_completed event. Parallel
        to ``audit_staleness.find_snapshot_commit`` recognizing chore(release)
        snapshots — kept narrow because ``audit_staleness`` keys on this exact
        header. The BROADER non-functional-type exclusion (generic
        chore/ci/docs/…) is Rule E, not this method.
        (B, 2026-06-02-compliance-detective-realign.)
        """
        return self.subject.strip().lower().startswith("chore(release)")

    def conventional_type(self) -> str | None:
        """The Conventional-Commit type of the subject (``ci(security): …`` →
        ``"ci"``; ``feat!: …`` → ``"feat"``), lowercased, or ``None`` when the
        subject has no ``type[(scope)][!]:`` prefix. Used by Rule E."""
        m = _CONVENTIONAL_TYPE_RE.match(self.subject.strip())
        return m.group(1).lower() if m else None


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
            # ``%s`` (subject) is appended for Rule D release-commit detection;
            # it is the last field so an embedded ``|`` in the subject is kept
            # intact by ``split("|", 2)``.
            ["show", "--no-patch", "--pretty=format:%ae|%P|%s", sha],
        )
    except RuntimeError as exc:
        return ScanError(str(exc))
    line = out.strip().splitlines()[0] if out.strip() else ""
    if "|" not in line:
        return ScanError(f"unparseable git show output for {sha}: {line!r}")
    parts = line.split("|", 2)
    email = parts[0]
    parents = parts[1] if len(parts) > 1 else ""
    subject = parts[2] if len(parts) > 2 else ""
    parent_count = len(parents.split()) if parents.strip() else 0

    try:
        diff_out = _run_git(repo, ["show", "--name-only", "--pretty=format:", sha])
    except RuntimeError as exc:
        return ScanError(str(exc))
    paths = tuple(p for p in diff_out.splitlines() if p.strip())
    return CommitInfo(sha=sha, author_email=email, parent_count=parent_count,
                      changed_paths=paths, subject=subject)


def commit_run_id(repo: Path, sha: str) -> str | None:
    """Return the ``Run-ID:`` trailer value of *sha*, or ``None``.

    Since ``iterate-2026-05-29-events-jsonl-worktree-commit`` a
    ``work_completed`` event ships ``commit:""`` BY DESIGN and links to its
    commit via the F6 commit's ``Run-ID:`` footer ↔ the event's ``adr_id``.
    B7 uses this to recognize a commit as covered when the matching event
    carries no SHA (C1, 2026-06-02-compliance-detective-realign).

    Soft-fails to ``None`` on any git error — the caller then treats the
    commit as un-linked (the safe, flagging direction).
    """
    try:
        body = _run_git(repo, ["show", "--no-patch", "--format=%B", sha])
    except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    match = _RUN_ID_TRAILER_RE.search(body)
    return match.group(1) if match else None


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
    """Apply Rules A/B/C/D/E and return the result.

    Each rule respects two flags:
    - ``retention.rule_a/b/c/d/e`` (top-level on/off switch)
    - the corresponding sub-key under ``b7_exclusions``

    Rule D (release-phase commits) stays NARROW — only ``chore(release)``
    headers — because ``audit_staleness`` keys on that exact header. Rule E is
    the BROADER policy: it excludes non-functional Conventional-Commit types
    (``build``/``chore``/``ci``/``docs``/``style``/``test`` by default —
    maintenance with no RTM footprint, so no work_completed event is expected).
    Functional types (``feat``/``fix``/``perf``/``refactor``) are NEVER excluded
    by Rule E — a feature/fix that bypassed the iterate flow is real drift B7
    keeps surfacing. Opt out via ``b7_exclusions.exclude_nonfunctional_types =
    false`` (old flag-everything stance) or override ``nonfunctional_types``.
    (iterate-2026-06-05-b7-exclude-nonfunctional supersedes B's narrow-Rule-D
    decision after the backfill treadmill it created.)
    """
    rule_a_on = retention.get("rule_a", True)
    rule_b_on = retention.get("rule_b", True)
    rule_c_on = retention.get("rule_c", True)
    rule_d_on = retention.get("rule_d", True)
    rule_e_on = retention.get("rule_e", True)

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

    if rule_d_on and exclusions.get("exclude_release_commits", True):
        if info.is_release_commit():
            return FilterResult(
                info, True,
                "chore(release) release-phase commit (Rule D)",
            )

    if rule_e_on and exclusions.get("exclude_nonfunctional_types", True):
        nonfunctional = {
            str(t).lower()
            for t in (exclusions.get("nonfunctional_types") or _NONFUNCTIONAL_TYPES)
        }
        ctype = info.conventional_type()
        if ctype is not None and ctype in nonfunctional:
            return FilterResult(
                info, True,
                f"non-functional {ctype} commit (Rule E)",
            )

    return FilterResult(info, False, "")
