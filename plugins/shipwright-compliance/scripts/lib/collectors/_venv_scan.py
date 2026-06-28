"""Cross-venv license resolution for the SBOM inventory.

The per-manifest resolver in ``_python_license.py`` reads only a manifest's
*own* ``.venv``; when that venv is unsynced at regeneration time the row falls
to ``-`` (``NOT_INSTALLED``) even though the package is installed in a sibling
workspace's venv. That fragility produced the dishonest committed ``sbom.md``
(AR-04). This module scans **every** ``.venv`` under the project so a package
installed anywhere resolves everywhere.

Used by the SBOM-inventory path only. The triage producer deliberately keeps
the strict per-manifest resolver (``_python_license.detect_python_license``).

Iterate 2026-06-28 (AR-04 SBOM data quality).
"""

from __future__ import annotations

from pathlib import Path

from ._license_const import NOT_INSTALLED, UNKNOWN_LICENSE
from ._python_license import (
    _canonical_pkg_name,
    _find_distinfo_candidates,
    _iter_site_packages_dirs,
    _parse_metadata_license,
)

# Directories never worth descending into when hunting for ``.venv`` dirs.
# ``.venv`` itself is matched explicitly below (it starts with ``.`` but IS the
# target), so it is NOT in this exclude set.
_VENV_SCAN_EXCLUDE = {
    "node_modules", ".git", "dist", "build", ".next", ".worktrees",
    "coverage", "__pycache__", ".pytest_cache", "site-packages",
}


def _find_venvs(project_root: Path, max_depth: int = 4) -> list[Path]:
    """All ``.venv`` directories under ``project_root`` (depth-limited, does not
    descend into a venv once found). Mirrors the collector's workspace walk."""
    found: list[Path] = []

    def _walk(dir_: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = list(dir_.iterdir())
        except (OSError, PermissionError):
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name == ".venv":
                found.append(entry)
                continue  # a venv is a leaf for this scan
            if entry.name in _VENV_SCAN_EXCLUDE or entry.name.startswith("."):
                continue
            _walk(entry, depth + 1)

    _walk(project_root, 0)
    # Deterministic order: license resolution returns the first real license
    # found, so a stable venv order keeps the output byte-identical across runs
    # / filesystems (the compliance determinism contract).
    return sorted(found)


def iter_all_site_packages(project_root: Path) -> list[Path]:
    """Every ``site-packages`` dir across all ``.venv``s under ``project_root``.

    Lets the SBOM resolve a package's license from ANY workspace venv, so a
    single unsynced manifest-local venv no longer drops a row to ``-`` — the
    root cause of the dishonest committed ``sbom.md`` (AR-04)."""
    out: list[Path] = []
    for venv in _find_venvs(project_root):
        out.extend(_iter_site_packages_dirs(venv.parent))
    return out


def detect_python_license_across(
    package_name: str, site_packages_dirs: list[Path]
) -> str:
    """Resolve a license by scanning ``site_packages_dirs`` (typically every
    venv under the project). A real license found in any venv wins immediately;
    a package installed-but-no-license in every venv resolves to
    ``UNKNOWN_LICENSE``; a package absent from EVERY venv is ``NOT_INSTALLED``.
    """
    canonical = _canonical_pkg_name(package_name)
    best = NOT_INSTALLED
    for site_packages in site_packages_dirs:
        matches = _find_distinfo_candidates(site_packages, canonical)
        if not matches:
            continue
        license_ = _parse_metadata_license(matches[-1])
        if license_ not in (NOT_INSTALLED, UNKNOWN_LICENSE):
            return license_
        best = UNKNOWN_LICENSE
    return best
