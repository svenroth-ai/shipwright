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
from ._python_license import (
    _canonical_pkg_name,
    parse_pyproject_dep_specs,
    parse_pyproject_deps,
)
from ._types import DependencyInfo
from ._uv_lock import load_lock_versions
from ._venv_scan import detect_python_license_across, iter_all_site_packages


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


def _collect_dependency_rows(
    project_root: Path,
) -> tuple[list[DependencyInfo], int, bool]:
    """Build the deduplicated SBOM dependency inventory + render metadata.

    Workspace-aware traversal (depth 3). Python **versions** come from the
    manifest's sibling ``uv.lock`` so a package declared at different specifier
    floors in two manifests dedupes to ONE row at the installed version (AR-04 —
    e.g. ``openai>=2.30.0`` + ``openai>=1.0.0`` -> ``2.30.0``). Python
    **licenses** resolve across ALL venvs (a stale manifest-local venv no longer
    drops a row to ``-``). npm is unchanged. No network, no subprocess.

    Returns ``(rows, merged_count, lock_used)``: ``merged_count`` drives the
    ``(deduplicated)`` summary annotation; ``lock_used`` the
    ``resolved from uv.lock`` header note.
    """
    deps: list[DependencyInfo] = []
    manifests = _find_manifests(project_root)
    merged = 0
    lock_used = False

    # npm — license + version from package.json/lockfile; dedup across
    # workspaces by (name, version, dep_type).
    seen_npm: set[tuple[str, str, str]] = set()
    for pkg_path in manifests["npm"]:
        manifest_dir = pkg_path.parent
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(pkg, dict):
            continue
        for section, dep_type in (("dependencies", "runtime"), ("devDependencies", "dev")):
            block = pkg.get(section)
            if not isinstance(block, dict):
                continue
            for name, version in block.items():
                key = (name, str(version), dep_type)
                if key in seen_npm:
                    merged += 1
                    continue
                seen_npm.add(key)
                deps.append(DependencyInfo(
                    name=name, version=version, dep_type=dep_type,
                    license=detect_npm_license(manifest_dir, name)))

    # python — version from sibling uv.lock; license across all venvs; dedup by
    # (canonical_name, installed_version, dep_type).
    all_site_packages = iter_all_site_packages(project_root)
    # Per-manifest lock versions + a project-wide UNION fallback. Version
    # resolution must be as robust as the (global) license scan: if one
    # manifest's uv.lock is missing/stale, a sibling lock's resolved version
    # still dedupes the row (else the duplicate-openai bug recurs on the next
    # unsynced regen — code-review finding #1). The manifest's OWN lock wins
    # first, so genuinely-divergent per-workspace versions stay distinct.
    manifest_locks = {p: load_lock_versions(p.parent) for p in manifests["python"]}
    global_lock: dict[str, str] = {}
    for lv in manifest_locks.values():
        for canon, ver in lv.items():
            global_lock.setdefault(canon, ver)

    seen_py: set[tuple[str, str, str]] = set()
    for pyproject_path in manifests["python"]:
        lock_versions = manifest_locks[pyproject_path]
        for name, floor, dep_type in parse_pyproject_dep_specs(pyproject_path):
            canonical = _canonical_pkg_name(name)
            installed = lock_versions.get(canonical) or global_lock.get(canonical)
            if installed:
                lock_used = True
            version = installed or floor
            key = (canonical, version, dep_type)
            if key in seen_py:
                merged += 1
                continue
            seen_py.add(key)
            deps.append(DependencyInfo(
                name=name, version=version, dep_type=dep_type,
                license=detect_python_license_across(name, all_site_packages)))

    return deps, merged, lock_used


def collect_dependencies(project_root: Path) -> list[DependencyInfo]:
    """Deduplicated SBOM dependency inventory (versions resolved from the
    lockfile, licenses from package metadata). See ``_collect_dependency_rows``
    for the version/dedup/license semantics; ``collect_all`` reads the
    merged-count + lock-used metadata via that function directly.
    """
    rows, _merged, _lock = _collect_dependency_rows(project_root)
    return rows


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
