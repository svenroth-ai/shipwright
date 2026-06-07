"""SBOM-facing collectors: dependencies + per-workspace undeclared groups.

Walks every ``package.json`` and ``pyproject.toml`` under the project
root (workspace-aware, depth 3, excludes ``node_modules`` / ``.venv``
/ build dirs). License resolution lives in ``_npm_license.py`` and
``_python_license.py`` so this module stays under the 300-LOC budget.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._license_const import UNKNOWN_LICENSE
from ._npm_license import detect_npm_license
from ._python_license import parse_pyproject_deps
from ._types import DependencyInfo


# Phase 0f (artifact-polish plan): workspace-aware traversal exclude list.
# Avoid descending into node_modules / .venv / build artifacts / Shipwright
# state when searching for manifests.
_WORKSPACE_EXCLUDE = {
    "node_modules", ".venv", "venv", ".git", "dist", "build", ".next",
    ".worktrees", ".shipwright", "coverage", "__pycache__", ".pytest_cache",
    "site-packages",
}


def _find_manifests(project_root: Path, max_depth: int = 3) -> dict[str, list[Path]]:
    """Locate package.json + pyproject.toml across the project tree.

    Returns {"npm": [Path, ...], "python": [Path, ...]} with each manifest
    directory deduplicated. Honors _WORKSPACE_EXCLUDE so node_modules etc.
    are not recursed into. ``max_depth`` is relative to project_root.
    """
    found: dict[str, list[Path]] = {"npm": [], "python": []}

    def _walk(dir_: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(dir_.iterdir())
        except (OSError, PermissionError):
            return
        # Capture manifests at this level.
        for entry in entries:
            if entry.is_file():
                if entry.name == "package.json":
                    found["npm"].append(entry)
                elif entry.name == "pyproject.toml":
                    found["python"].append(entry)
        # Recurse into subdirs (skip excluded names + hidden, except .shipwright is excluded above).
        for entry in entries:
            if entry.is_dir() and entry.name not in _WORKSPACE_EXCLUDE and not entry.name.startswith("."):
                _walk(entry, depth + 1)

    _walk(project_root, 0)
    return found


def collect_dependencies(project_root: Path) -> list[DependencyInfo]:
    """Read dependencies from every package.json + pyproject.toml under project_root.

    Phase 0f (artifact-polish plan): workspace-aware traversal (depth 3,
    excludes node_modules / .venv / build dirs / .shipwright). License
    resolution is lockfile-first for JS (package-lock.json v3) and
    importlib.metadata for Python (reads installed site-packages after
    `uv sync`). No network, no subprocess.
    """
    deps: list[DependencyInfo] = []
    manifests = _find_manifests(project_root)

    # Track dedup across workspaces: (name, version, dep_type) per manifest.
    # Multiple manifests legitimately re-declare deps; we keep one row per
    # (name, version) pair to keep the SBOM clean.
    seen: set[tuple[str, str, str]] = set()

    for pkg_path in manifests["npm"]:
        manifest_dir = pkg_path.parent
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for name, version in pkg.get("dependencies", {}).items():
            key = (name, str(version), "runtime")
            if key in seen:
                continue
            seen.add(key)
            license_ = detect_npm_license(manifest_dir, name)
            deps.append(DependencyInfo(name=name, version=version, dep_type="runtime", license=license_))
        for name, version in pkg.get("devDependencies", {}).items():
            key = (name, str(version), "dev")
            if key in seen:
                continue
            seen.add(key)
            license_ = detect_npm_license(manifest_dir, name)
            deps.append(DependencyInfo(name=name, version=version, dep_type="dev", license=license_))

    for pyproject_path in manifests["python"]:
        for dep in parse_pyproject_deps(pyproject_path):
            key = (dep.name, dep.version, dep.dep_type)
            if key in seen:
                continue
            seen.add(key)
            deps.append(dep)

    return deps


def collect_undeclared_by_workspace(project_root: Path) -> list[dict]:
    """Group genuinely-undeclared packages (``license == UNKNOWN_LICENSE``,
    i.e. resolved but no declared license) by their manifest. ``NOT_INSTALLED``
    packages are excluded — not installed in the scan env is a scan artifact,
    not a triage finding.

    Iterate B.2 (ADR-054 D1 / ADR-056) — feeds the SBOM triage producer.
    ``collect_dependencies`` collapses cross-workspace duplicates into a
    single row, which is right for the SBOM table but wrong for triage:
    the operator needs to know *which* workspace to ``cd`` into, so we
    re-scan manifests without deduping and partition by manifest path.

    Returns a list of dicts (one per manifest with >0 undeclared entries)::

        {
          "manifest_rel_path": "client/package.json",   # POSIX-style
          "manifest_type": "npm" | "python",
          "undeclared": [{"name": "react", "version": "^19.0.0"}, ...],
        }

    Manifests with all licenses resolved are omitted (no work for the
    operator → no triage item). Honors the same ``_WORKSPACE_EXCLUDE``
    list as ``collect_dependencies``. Path components are joined with
    ``/`` so the dedup-key shape is identical on Linux + Windows.
    """
    project_root = Path(project_root).resolve()
    manifests = _find_manifests(project_root)
    groups: list[dict] = []

    for pkg_path in manifests["npm"]:
        manifest_dir = pkg_path.parent
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(pkg, dict):
            continue
        undeclared: list[dict] = []
        for section in ("dependencies", "devDependencies"):
            section_deps = pkg.get(section)
            # Reviewer-flagged M1: a malformed package.json with
            # `"dependencies": []` (list/null/string) would AttributeError
            # on `.items()` and abort the whole sweep. Guard at the
            # section boundary, mirroring the JSONDecodeError skip above.
            if not isinstance(section_deps, dict):
                continue
            for name, version in section_deps.items():
                # Only genuine "resolved but no declared license" (Fall 2) is a
                # triage finding. NOT_INSTALLED (scan artifact) is excluded.
                if detect_npm_license(manifest_dir, name) == UNKNOWN_LICENSE:
                    undeclared.append({"name": name, "version": str(version)})
        if undeclared:
            rel = pkg_path.relative_to(project_root).as_posix()
            groups.append({
                "manifest_rel_path": rel,
                "manifest_type": "npm",
                "undeclared": undeclared,
            })

    for pyproject_path in manifests["python"]:
        undeclared = []
        for dep in parse_pyproject_deps(pyproject_path):
            # Fall 2 only (see npm branch): NOT_INSTALLED stays silent.
            if dep.license == UNKNOWN_LICENSE:
                undeclared.append({"name": dep.name, "version": dep.version})
        if undeclared:
            rel = pyproject_path.relative_to(project_root).as_posix()
            groups.append({
                "manifest_rel_path": rel,
                "manifest_type": "python",
                "undeclared": undeclared,
            })

    return groups
