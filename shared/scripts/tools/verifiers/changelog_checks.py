"""Changelog-phase verifier checks.

Iterate 12.4 brings the ``shipwright-changelog`` plugin to Minimum
Phase Completion Canon coverage at C1/C2/C3 only plus two Sonder-Checks
unique to the release-tagging workflow:

- **C4 skipped**: release tagging is process management, not an
  architectural decision.
- **C5 not applicable**: this plugin OWNS the ``[Unreleased]`` → version
  prepend. Appending to ``[Unreleased]`` after a release would collide
  with the next version's notes.

Sonder-Checks:

- ``check_git_tag_exists`` — the plugin's Step 6 creates a ``vX.Y.Z``
  git tag; this check reads the top version header from CHANGELOG.md
  and confirms the matching tag exists in the repo. ERROR.
- ``check_changelog_version_matches_tag`` — the most recent
  ``## [vX.Y.Z]`` heading in CHANGELOG.md must match the most recent
  ``vX.Y.Z`` git tag (by string, not recency). Catches "tag pushed but
  CHANGELOG not regenerated" drift. ERROR.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_phase_history_has_run,
    find_changelog,
)


_VERSION_HEADING_RE = re.compile(
    r"^##\s+\[(v?\d+\.\d+\.\d+[^\]]*)\]",
    re.MULTILINE,
)
_VERSION_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+")


def _extract_latest_version_from_changelog(project_root: Path) -> str | None:
    """Return the first non-``Unreleased`` version heading in
    ``CHANGELOG.md``, or None if not present.

    Scans top-down and picks the first ``## [vX.Y.Z]`` header after
    any ``[Unreleased]`` block — i.e. the most recently released
    version. Case-insensitive on the ``v`` prefix (both ``v1.2.3`` and
    ``1.2.3`` work; we normalise to include ``v``).
    """
    changelog = find_changelog(project_root)
    if changelog is None:
        return None
    try:
        content = changelog.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    for m in _VERSION_HEADING_RE.finditer(content):
        version = m.group(1).strip()
        if version.lower() == "unreleased":
            continue
        if not version.lower().startswith("v"):
            version = "v" + version
        return version
    return None


def _git_tag_exists(project_root: Path, tag: str) -> tuple[bool, str]:
    """Return ``(exists, detail)`` — run ``git rev-parse --verify <tag>``
    and interpret a clean exit 0 as "tag exists".

    Returns ``(False, "<reason>")`` on any error (git missing, tag
    missing, subprocess failure) so callers can report accurately.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"git lookup failed: {exc}"
    if result.returncode == 0:
        return True, result.stdout.strip()
    return False, f"tag not found (rc={result.returncode})"


def _latest_git_version_tag(project_root: Path) -> str | None:
    """Return the lexicographically latest ``vX.Y.Z`` tag in the repo,
    or None if no tags exist. Uses ``git tag --list`` so we don't need
    GitPython as a dep.
    """
    try:
        result = subprocess.run(
            ["git", "tag", "--list", "v*", "--sort=-v:refname"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        line = line.strip()
        if _VERSION_TAG_RE.match(line):
            return line
    return None


# ---------------------------------------------------------------------------
# Sonder-Checks
# ---------------------------------------------------------------------------

def check_git_tag_exists(project_root: Path) -> CheckResult:
    """For the latest ``## [vX.Y.Z]`` heading in CHANGELOG.md, confirm
    the matching git tag exists locally. ERROR on mismatch.
    """
    name = "release tag exists in git"
    version = _extract_latest_version_from_changelog(project_root)
    if version is None:
        return CheckResult(
            name, False, "no released version found in CHANGELOG.md",
            severity=Severity.WARNING.value,
        )
    exists, detail = _git_tag_exists(project_root, version)
    if not exists:
        return CheckResult(name, False, f"{version}: {detail}")
    return CheckResult(name, True, f"{version} present in git")


def check_changelog_version_matches_tag(project_root: Path) -> CheckResult:
    """The top released ``## [vX.Y.Z]`` in CHANGELOG.md must equal the
    latest ``v*`` git tag. Catches "tag pushed but CHANGELOG forgot to
    regenerate" drift.
    """
    name = "CHANGELOG top version matches latest git tag"
    cl_version = _extract_latest_version_from_changelog(project_root)
    git_version = _latest_git_version_tag(project_root)
    if cl_version is None and git_version is None:
        return CheckResult(name, True, "no releases yet — nothing to verify")
    if cl_version is None:
        return CheckResult(
            name, False,
            f"git has tag {git_version} but CHANGELOG.md has no released version",
        )
    if git_version is None:
        return CheckResult(
            name, False,
            f"CHANGELOG.md has {cl_version} but no matching git tag exists",
        )
    if cl_version != git_version:
        return CheckResult(
            name, False,
            f"CHANGELOG top={cl_version} != latest git tag={git_version}",
        )
    return CheckResult(name, True, f"{cl_version} matches latest git tag")


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_changelog_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full changelog-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    # Sonder-Checks
    results.append(check_git_tag_exists(project_root))
    results.append(check_changelog_version_matches_tag(project_root))

    # Canon (C4 skipped, C5 n/a)
    results.append(check_c1_phase_event_recorded(project_root, "changelog"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "changelog"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "changelog"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "changelog", run_id))

    # ADR integrity
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    return run_changelog_checks(project_root, run_id=run_id)


__all__ = [
    "Severity",
    "check_changelog_version_matches_tag",
    "check_git_tag_exists",
    "run_all_checks",
    "run_changelog_checks",
]
