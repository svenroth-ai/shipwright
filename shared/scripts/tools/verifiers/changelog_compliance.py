"""Changelog-phase workflow compliance checks (Phase-Quality PR 2).

Implements W6 — git-tag existence for the top released version in
``CHANGELOG.md``. Thin wrapper around
``changelog_checks.check_git_tag_exists`` so the workflow category
reuses the autoritative tag-lookup logic (plan § 3).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    make_finding,
)
from tools.verifiers.changelog_checks import check_git_tag_exists  # noqa: E402
from tools.verifiers.common import Severity  # noqa: E402


W6_NAME = "W6 git tag for released version"
W6_REMEDIATION = (
    "Run `git tag vX.Y.Z` + `git push --tags` after the CHANGELOG top "
    "version was written, or regenerate CHANGELOG.md to drop the stale "
    "release block."
)


def check_w6_git_tag_exists(project_root: Path) -> dict[str, Any]:
    result = check_git_tag_exists(project_root)
    if result.is_skipped:
        return make_finding("W6", STATUS_SKIP, result.detail, name=W6_NAME)
    if result.ok:
        return make_finding(
            "W6", STATUS_PASS, result.detail or "tag present",
            name=W6_NAME,
        )
    if result.severity == Severity.WARNING.value:
        return make_finding(
            "W6", STATUS_WARN, result.detail,
            name=W6_NAME,
            remediation=W6_REMEDIATION,
        )
    return make_finding(
        "W6", STATUS_FAIL, result.detail,
        name=W6_NAME,
        remediation=W6_REMEDIATION,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [check_w6_git_tag_exists(project_root)]


__all__ = ["check_w6_git_tag_exists", "run"]
