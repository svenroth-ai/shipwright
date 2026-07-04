"""dependency_signal — LOCAL lockfile/manifest → license hygiene (dim 7).

Reuses the compliance SBOM collectors (``collect_dependencies``) and license
partition (``sbom_render._classify`` / ``is_copyleft``) rather than re-deriving
them — the grader's dep hygiene is the same accounting the dashboard SBOM uses.

**Cold-repo honesty (the key rule).** A package the scanner could not resolve at
all (``NOT_INSTALLED`` — no ``.venv``/``node_modules`` present) is a property of
*our scan environment*, not the repo's hygiene, so it is **excluded** from the
graded set (mirroring ``collect_undeclared_by_workspace``). We grade only the
deps we could actually inspect (a real license, or installed-but-undeclared). If
nothing is inspectable → ``n/a`` (honest: "licenses not resolved without
install"), never a fabricated low score. No network, no package-manager exec.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from reuse_bridge import load_collect_dependencies, load_license_classifier


@dataclass(frozen=True)
class DependencySignal:
    """License-hygiene over the *inspectable* dependency set."""

    measurable: bool
    deps_total: int            # inspectable = resolved + installed-but-undeclared
    deps_unknown_license: int
    deps_copyleft: int
    detail: str
    excluded_not_installed: int


def _na(detail: str, excluded: int = 0) -> DependencySignal:
    return DependencySignal(
        measurable=False, deps_total=0, deps_unknown_license=0,
        deps_copyleft=0, detail=detail, excluded_not_installed=excluded)


def compute_dependency_signal(
    root: Path,
    *,
    collect: Callable[[Path], list[Any]] | None = None,
    classifier: tuple[Callable, Callable] | None = None,
) -> DependencySignal:
    """License hygiene over the inspectable deps of ``root``; ``n/a`` otherwise."""
    collect = collect or load_collect_dependencies()
    classify, _is_copyleft = classifier or load_license_classifier()
    try:
        deps = list(collect(root))
    except Exception:  # hostile/unsupported manifest → graceful n/a, never a crash
        return _na("dependency manifest could not be parsed")

    if not deps:
        return _na("no dependency manifest")

    resolved, no_license, not_installed, copyleft = classify(deps)
    inspectable = len(resolved) + len(no_license)
    if inspectable == 0:
        return _na(
            f"{len(not_installed)} dependencies declared; "
            "licenses not resolved without install",
            excluded=len(not_installed))

    unknown = len(no_license)
    copyleft_n = len(copyleft)
    detail = (
        f"{unknown}/{inspectable} inspected deps without a declared license; "
        f"{copyleft_n} copyleft")
    if not_installed:
        detail += f" ({len(not_installed)} not resolved without install)"
    return DependencySignal(
        measurable=True, deps_total=inspectable, deps_unknown_license=unknown,
        deps_copyleft=copyleft_n, detail=detail,
        excluded_not_installed=len(not_installed))
