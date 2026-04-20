"""Walk a project's top-level folders and assign them to architecture layers.

Used by /shipwright-adopt to populate architecture.md Layers section.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Heuristic layer mapping — matched by folder name (case-insensitive).
_LAYER_HINTS: list[tuple[str, list[str]]] = [
    ("presentation", [
        "pages", "app", "components", "views", "routes", "screens",
        "layouts", "ui", "templates",
    ]),
    ("domain", [
        "lib", "core", "domain", "models", "entities", "services",
        "business", "logic",
    ]),
    ("data", [
        "db", "database", "repositories", "repo", "persistence",
        "storage", "dal", "supabase",
    ]),
    ("infrastructure", [
        "infra", "infrastructure", "config", "deploy", "scripts",
        "tools", "docker",
    ]),
    ("api", ["api", "routes", "handlers", "controllers", "endpoints"]),
    ("tests", ["tests", "test", "__tests__", "spec", "e2e", "integration"]),
    ("docs", ["docs", "documentation", "doc"]),
    ("static", ["public", "static", "assets"]),
]

# Files to count for LOC (approximate).
_CODE_EXTENSIONS = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".go", ".rs", ".rb", ".php", ".java", ".kt", ".swift",
    ".sql", ".sh", ".bash",
})

_IGNORE_DIRS = frozenset({
    "node_modules", "__pycache__", ".git", ".venv", "dist", "build",
    ".next", ".nuxt", "target", "coverage", "playwright-report",
    "test-results", ".turbo", ".svelte-kit",
})


def _count_loc(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _CODE_EXTENSIONS:
            continue
        try:
            total += sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return total


def _classify_folder(name: str) -> str | None:
    lower = name.lower()
    for layer, hints in _LAYER_HINTS:
        for hint in hints:
            if lower == hint or lower.startswith(hint + "-") or lower.endswith("-" + hint):
                return layer
    return None


def introspect_folders(
    project_root: Path,
    excludes: set[str] | None = None,
) -> dict[str, Any]:
    """Return folder→layer mapping with LOC per layer.

    Walks top-level + one-deep ``src/`` children. Excluded paths are
    respected (relative POSIX form).
    """
    excludes = excludes or set()
    layers: dict[str, list[str]] = {}
    loc_by_layer: dict[str, int] = {}

    def _is_excluded(rel: str) -> bool:
        return any(rel == e or rel.startswith(e + "/") for e in excludes)

    def _record(path: Path) -> None:
        rel = path.relative_to(project_root).as_posix()
        if _is_excluded(rel):
            return
        layer = _classify_folder(path.name)
        if layer is None:
            return
        layers.setdefault(layer, []).append(rel)
        loc_by_layer[layer] = loc_by_layer.get(layer, 0) + _count_loc(path)

    # Top-level scan
    for child in sorted(project_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in _IGNORE_DIRS or child.name.startswith("."):
            continue
        _record(child)

    # One-deep under src/ (Next/React/TS projects commonly nest there)
    src = project_root / "src"
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if not child.is_dir():
                continue
            _record(child)

    return {
        "layers": [
            {"name": layer, "paths": sorted(paths)}
            for layer, paths in sorted(layers.items())
        ],
        "loc_by_layer": loc_by_layer,
    }
