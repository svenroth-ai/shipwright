"""Detect CI/CD provider and workflow files for /shipwright-adopt."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_ci(project_root: Path) -> dict[str, Any]:
    """Return CI provider + workflow file list. Pure, read-only."""
    gh_dir = project_root / ".github" / "workflows"
    if gh_dir.is_dir():
        workflows = sorted(
            p.relative_to(project_root).as_posix()
            for p in gh_dir.glob("*.yml")
        ) + sorted(
            p.relative_to(project_root).as_posix()
            for p in gh_dir.glob("*.yaml")
        )
        return {"provider": "github-actions", "workflows": workflows}

    gitlab = project_root / ".gitlab-ci.yml"
    if gitlab.exists():
        return {"provider": "gitlab-ci", "workflows": [".gitlab-ci.yml"]}

    circle = project_root / ".circleci" / "config.yml"
    if circle.exists():
        return {"provider": "circleci", "workflows": [".circleci/config.yml"]}

    jenkins = project_root / "Jenkinsfile"
    if jenkins.exists():
        return {"provider": "jenkins", "workflows": ["Jenkinsfile"]}

    travis = project_root / ".travis.yml"
    if travis.exists():
        return {"provider": "travis", "workflows": [".travis.yml"]}

    return {"provider": None, "workflows": []}
