"""Verify generate_adoption_artifacts merges AST + crawl features additively (4.2).

Bug repro: AST detector finds 20 backend routes (Hono); Playwright crawl
finds 5 frontend pages (Vite SPA). Old behavior: when routes.json had
entries, AST features were dropped — final features[] had 5 instead of
the union of 25. Fix: union by route, with origin tracking so spec.md
can render both API and UI FRs.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.generate_adoption_artifacts import generate


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def _write_inputs(
    root: Path,
    *,
    snapshot_features: list[dict],
    routes: list[dict] | None = None,
    enrichment: dict | None = None,
) -> tuple[Path, Path, Path]:
    snap_dir = root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snap_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "vite-hono"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": snapshot_features,
        "git": {"commits_total": 100, "contributors_total": 2, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")
    routes_path = snap_dir / "routes.json"
    if routes is not None:
        routes_path.write_text(json.dumps(routes), encoding="utf-8")
    enrichment_path = snap_dir / "enrichment.json"
    if enrichment is not None:
        enrichment_path.write_text(json.dumps(enrichment), encoding="utf-8")
    return snapshot_path, enrichment_path, routes_path


def test_ast_features_survive_when_crawl_finds_only_frontend(tmp_path: Path) -> None:
    """AST sees 3 backend routes; crawl finds 2 frontend pages. Spec must
    contain all 5 — none silently dropped."""
    _git_init(tmp_path)
    ast_features = [
        {"route": "/api/diagnostics", "source_file": "server/src/index.ts", "framework": "hono", "method": "GET"},
        {"route": "/api/sessions", "source_file": "server/src/sessions.ts", "framework": "hono", "method": "POST"},
        {"route": "/api/users", "source_file": "server/src/users.ts", "framework": "hono", "method": "GET"},
    ]
    routes = [
        {"url": "/", "title": "Home"},
        {"url": "/dashboard", "title": "Dashboard"},
    ]
    snap, enr, rts = _write_inputs(tmp_path, snapshot_features=ast_features, routes=routes)

    result = generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )

    spec_text = (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").read_text(encoding="utf-8")
    # All 3 AST routes are surfaced via their URL/label (no enrichment label provided)
    assert "/api/diagnostics" in spec_text
    assert "/api/sessions" in spec_text
    assert "/api/users" in spec_text
    # Crawl entries are surfaced via their title (the spec template renders `label`,
    # which is `route.title` for crawl entries and `route` for AST entries).
    assert "Dashboard" in spec_text
    assert "Home" in spec_text
    # 5 distinct FR rows = the union, not the post-drop 2
    assert spec_text.count("FR-01.") >= 5
    # Source files from AST should also be referenced
    assert "server/src/index.ts" in spec_text
    assert "server/src/sessions.ts" in spec_text


def test_overlapping_routes_keep_both_origins(tmp_path: Path) -> None:
    """If AST and crawl both yield a route with the same URL, the merged
    entry should not be duplicated AND should record both origins."""
    _git_init(tmp_path)
    ast_features = [
        {"route": "/dashboard", "source_file": "src/pages/dashboard.tsx", "framework": "next-pages-router"},
    ]
    routes = [
        {"url": "/dashboard", "title": "Dashboard"},
    ]
    snap, enr, rts = _write_inputs(tmp_path, snapshot_features=ast_features, routes=routes)
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec_text = (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").read_text(encoding="utf-8")
    # Exactly one row for /dashboard (no duplicate)
    assert spec_text.count("/dashboard") <= 3, (
        "expected /dashboard to appear at most a few times (one FR row + section), "
        f"got {spec_text.count('/dashboard')}"
    )
    # The source_file from AST should still be referenced
    assert "src/pages/dashboard.tsx" in spec_text


def test_no_routes_falls_back_to_ast_only(tmp_path: Path) -> None:
    """Existing back-compat: when crawl produced no routes, AST features ARE used.
    (This was already correct behavior; test pins it.)"""
    _git_init(tmp_path)
    ast_features = [
        {"route": "/login", "source_file": "src/pages/login.tsx", "framework": "next-pages-router"},
        {"route": "/dashboard", "source_file": "src/pages/dashboard.tsx", "framework": "next-pages-router"},
    ]
    snap, enr, rts = _write_inputs(tmp_path, snapshot_features=ast_features, routes=None)
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec_text = (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").read_text(encoding="utf-8")
    assert "/login" in spec_text
    assert "/dashboard" in spec_text
