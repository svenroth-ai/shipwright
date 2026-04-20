"""AST-based feature inference (fallback when Playwright crawl unavailable).

Enumerates routes from common web frameworks by scanning for conventional
file layouts. This is the Layer-1 fallback used when /shipwright-adopt
cannot run a dev-server + Playwright crawl.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _is_excluded(rel_path: str, excludes: set[str]) -> bool:
    return any(rel_path == e or rel_path.startswith(e + "/") for e in excludes)


def _next_app_router(project_root: Path, excludes: set[str]) -> list[dict[str, Any]]:
    """Scan src/app/**/page.tsx or app/**/page.tsx for Next.js App Router."""
    features: list[dict[str, Any]] = []
    for root_name in ("src/app", "app"):
        base = project_root / root_name
        if not base.is_dir():
            continue
        for page_file in base.rglob("page.*"):
            if page_file.suffix not in {".tsx", ".ts", ".jsx", ".js"}:
                continue
            rel = page_file.relative_to(project_root).as_posix()
            if _is_excluded(rel, excludes):
                continue
            # Convert folder path to route: src/app/dashboard/page.tsx -> /dashboard
            # Remove `src/app/` or `app/` prefix and `/page.ext` suffix.
            path_parts = page_file.parent.relative_to(base).parts
            # Next.js route-group convention: (group) is not part of route
            route_parts = [p for p in path_parts if not (p.startswith("(") and p.endswith(")"))]
            route = "/" + "/".join(route_parts) if route_parts else "/"
            features.append({
                "route": route,
                "source_file": rel,
                "framework": "next-app-router",
                "confidence": 0.9,
            })
    return features


def _next_pages_router(project_root: Path, excludes: set[str]) -> list[dict[str, Any]]:
    """Scan pages/ for Next.js Pages Router (older convention)."""
    features: list[dict[str, Any]] = []
    for root_name in ("src/pages", "pages"):
        base = project_root / root_name
        if not base.is_dir():
            continue
        for page_file in base.rglob("*.tsx"):
            if page_file.name.startswith("_"):
                continue  # _app.tsx, _document.tsx
            rel = page_file.relative_to(project_root).as_posix()
            if _is_excluded(rel, excludes):
                continue
            # pages/dashboard.tsx -> /dashboard
            # pages/blog/[slug].tsx -> /blog/[slug]
            stem = page_file.stem
            route_parts = list(page_file.parent.relative_to(base).parts)
            if stem != "index":
                route_parts.append(stem)
            route = "/" + "/".join(route_parts) if route_parts else "/"
            features.append({
                "route": route,
                "source_file": rel,
                "framework": "next-pages-router",
                "confidence": 0.85,
            })
    return features


_EXPRESS_ROUTE_RE = re.compile(
    r"""(?:app|router)\.(get|post|put|patch|delete|all)\(\s*['"]([^'"]+)['"]""",
)
_FASTAPI_ROUTE_RE = re.compile(
    r"""@(?:app|router)\.(get|post|put|patch|delete)\(\s*['"]([^'"]+)['"]""",
)
_FLASK_ROUTE_RE = re.compile(
    r"""@(?:app|bp|blueprint)\.route\(\s*['"]([^'"]+)['"]""",
)


def _scan_js_routes(project_root: Path, excludes: set[str]) -> list[dict[str, Any]]:
    """Grep-style route extraction from JS/TS server files."""
    features: list[dict[str, Any]] = []
    candidates = []
    for pattern in ("src/**/*.ts", "src/**/*.js", "server/**/*.ts", "server/**/*.js"):
        candidates.extend(project_root.glob(pattern))
    for f in candidates[:200]:
        if not f.is_file():
            continue
        rel = f.relative_to(project_root).as_posix()
        if _is_excluded(rel, excludes):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _EXPRESS_ROUTE_RE.finditer(content):
            method, route = m.group(1).upper(), m.group(2)
            features.append({
                "route": route,
                "source_file": rel,
                "framework": "express",
                "method": method,
                "confidence": 0.75,
            })
    return features


def _scan_py_routes(project_root: Path, excludes: set[str]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    candidates = list(project_root.rglob("*.py"))[:500]
    for f in candidates:
        rel = f.relative_to(project_root).as_posix()
        if _is_excluded(rel, excludes):
            continue
        if any(p in rel.split("/") for p in ("__pycache__", ".venv", "venv", "tests")):
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _FASTAPI_ROUTE_RE.finditer(content):
            method, route = m.group(1).upper(), m.group(2)
            features.append({
                "route": route,
                "source_file": rel,
                "framework": "fastapi",
                "method": method,
                "confidence": 0.8,
            })
        for m in _FLASK_ROUTE_RE.finditer(content):
            route = m.group(1)
            features.append({
                "route": route,
                "source_file": rel,
                "framework": "flask",
                "confidence": 0.75,
            })
    return features


def infer_features_ast(
    project_root: Path,
    stack: dict[str, Any],
    excludes: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the combined AST-based feature list. De-duplicates by route.

    This is the Layer-1 fallback — used only when Layer-1.5 (Playwright crawl)
    is unavailable or skipped.
    """
    excludes = excludes or set()
    raw: list[dict[str, Any]] = []

    # Framework-specific extraction
    if "next" in stack.get("frontend", {}):
        raw.extend(_next_app_router(project_root, excludes))
        raw.extend(_next_pages_router(project_root, excludes))
    if stack.get("primary_language") in {"typescript", "javascript", "mixed"}:
        raw.extend(_scan_js_routes(project_root, excludes))
    if stack.get("primary_language") in {"python", "mixed"}:
        raw.extend(_scan_py_routes(project_root, excludes))

    # De-duplicate by (route, framework) — Next App Router can overlap with /app scan
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in raw:
        key = (item["route"], item.get("framework", ""))
        if key in seen:
            continue
        seen.add(key)
        # Auto-assign an FR-ID in sequence
        item["fr_id"] = f"FR-01.{len(deduped) + 1:02d}"
        deduped.append(item)
    return deduped
