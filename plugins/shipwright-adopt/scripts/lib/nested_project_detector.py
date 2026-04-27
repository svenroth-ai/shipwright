"""Detect nested sub-projects (like webui/ inside the shipwright monorepo).

A nested project is a directory that has its own project-management
state — own .git/, own shipwright_run_config.json, or its own
package.json that is clearly independent from the parent.

Used by /shipwright-adopt to avoid inadvertently adopting sub-projects
that should be handled separately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Top-level dirs that are definitely NOT nested projects (build artifacts,
# caches, dependencies).
_NEVER_NESTED: frozenset[str] = frozenset({
    "node_modules", "__pycache__", "dist", "build", ".venv", ".git",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".idea", ".vscode",
    "vendor", "target", "e2e-results", "playwright-report", "test-results",
    "coverage", ".next", ".nuxt", ".turbo", ".svelte-kit",
})


def detect_nested_projects(project_root: Path, max_depth: int = 2) -> list[dict[str, Any]]:
    """Return a list of nested-project candidates found in the repo.

    Walks up to ``max_depth`` levels deep. Each candidate:
        {"path": "<relative-posix>", "markers": [...], "reason": "<short>"}

    Markers that flag a nested project:
      - has own `.git/` directory (submodule or separate clone)
      - has own `shipwright_run_config.json` (separate Shipwright project)
      - has own `package.json` AND is at depth >= 1 (workspace / sub-app)
      - has own `pyproject.toml` AND is at depth >= 1
    """
    candidates: list[dict[str, Any]] = []

    def _scan(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        if not current.is_dir():
            return
        for child in sorted(current.iterdir()):
            if not child.is_dir():
                continue
            name = child.name
            if name.startswith(".") and name != ".github":
                continue
            if name in _NEVER_NESTED:
                continue
            markers: list[str] = []
            reasons: list[str] = []
            if (child / ".git").exists():
                markers.append(".git")
                reasons.append("nested-git")
            if (child / "shipwright_run_config.json").exists():
                markers.append("shipwright_run_config.json")
                reasons.append("separate-shipwright-project")
            if (child / "CLAUDE.md").exists() and (child / ".shipwright" / "agent_docs").is_dir():
                markers.append("CLAUDE.md+.shipwright/agent_docs/")
                reasons.append("has-own-shipwright-artifacts")
            # package.json / pyproject.toml in a subdir suggests a workspace,
            # but only flag if there's ALSO something else (to avoid noise
            # from standard monorepo layouts like apps/*/ which may be
            # intentional parts of the project).
            if depth >= 1:
                if (child / "package.json").exists() and markers:
                    markers.append("package.json")
                if (child / "pyproject.toml").exists() and markers:
                    markers.append("pyproject.toml")
            if markers:
                candidates.append({
                    "path": child.relative_to(project_root).as_posix(),
                    "markers": markers,
                    "reason": reasons[0] if reasons else "separate-workspace",
                })
            # Only recurse into direct subdirs (depth < max_depth); don't
            # descend into already-flagged nested projects.
            if depth + 1 <= max_depth and not markers:
                _scan(child, depth + 1)

    _scan(project_root, depth=0)
    return candidates
